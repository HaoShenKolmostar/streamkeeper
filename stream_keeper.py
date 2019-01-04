import signal
import time
import threading
import datetime
import shutil
import os
from os import system as system_call
from serial.tools.list_ports_posix import comports
from streamer_keeper_config import (
    START_HOUR, START_MIN, STOP_HOUR, STOP_MIN,
    S3_BASE, BUCKET, KIND, CITY, TAG, VENDER, BOARD, USER,
    COLLECT_FOLDER, BIN_NAME, MCU_DIR, AXF_NAME)


MCU_VIRTUAL_COM_FLAG = 'MCU VIRTUAL COM'
LOOP_INTERVAL = 20
LOAD_AXF_INTERVAL = 10
TIME_DELTA_TOLERANCE = 1


def time_almost_equal(hour, minute):
    dt = datetime.datetime.now()
    if not hour == dt.hour:
        return False
    return abs(dt.minute - minute) < TIME_DELTA_TOLERANCE


def load_axf():
    command = '{}/ide/bin/crt_emu_cm_redlink --flash-load-exec {} -p LPC54114J256 --rst'.format(
        MCU_DIR, AXF_NAME
    )
    return system_call(command) == 0


def run_streamer(port):
    command = './{} {} >> streamer.log'.format(
        BIN_NAME, port
    )
    return system_call(command) == 0


def get_mcu_virturl_com():
    iterator = sorted(comports())
    for n, (port, desc, hwid) in enumerate(iterator, 1):
        if MCU_VIRTUAL_COM_FLAG in desc:
            return os.path.basename(port)
    return None


def upload_folder(collect_folder, target_folder):
    print('start_uploading')
    command = 'aws s3 sync ./{} {}{}/{}/{}/{}/{}/{}/{} --profile {}'.format(
        collect_folder,
        S3_BASE, BUCKET, KIND, CITY, TAG, VENDER, BOARD,
        target_folder, USER
    )
    try:
        return system_call(command) == 0
    except Exception as e:
        return False


def handle_collect_folder():
    target_folder = datetime.datetime.now().strftime('%Y%m%d')
    if not os.path.exists(COLLECT_FOLDER):
        raise ChildProcessError(
            'No data available in {}'.format(COLLECT_FOLDER))
    print('start uploading')
    while True:
        success = upload_folder(COLLECT_FOLDER, target_folder)
        if success:
            shutil.rmtree(COLLECT_FOLDER)
            print('uploading finished')
            return True
        else:
            time.sleep(LOOP_INTERVAL)
            continue


def kill_progresses():
    port = get_mcu_virturl_com()
    psaux_out = os.popen(
        "ps aux | grep \'{} {}\'".format(BIN_NAME, port)).read()
    if not psaux_out:
        return
    GREP_FLAG = 'grep'
    for line in psaux_out.splitlines():
        if port in line and GREP_FLAG not in line:
            pid = int(line.split()[1])
            os.kill(pid, signal.SIGKILL)


class CollectThread(threading.Thread):
    def __init__(self, port):
        threading.Thread.__init__(self)
        self.port = port

    def run(self):
        run_streamer(self.port)


class Worker:
    def __init__(self):
        self.thread = None

    def run_start_loop(self):
        while(True):
            time.sleep(LOOP_INTERVAL)
            if not os.path.exists(COLLECT_FOLDER):
                os.makedirs(COLLECT_FOLDER)
            if not time_almost_equal(START_HOUR, START_MIN):
                continue
            load_axf()
            time.sleep(LOAD_AXF_INTERVAL)
            port = get_mcu_virturl_com()
            if not port:
                continue
            self.thread = CollectThread(port)
            self.thread.start()
            return

    def run_stop_loop(self):
        while True:
            time.sleep(LOOP_INTERVAL)
            if not time_almost_equal(STOP_HOUR, STOP_MIN):
                continue
            else:
                break
        time.sleep(LOOP_INTERVAL)
        self.thread.stopped = True
        kill_progresses()
        handle_collect_folder()


worker = Worker()
while True:
    worker.run_start_loop()
    worker.run_stop_loop()
