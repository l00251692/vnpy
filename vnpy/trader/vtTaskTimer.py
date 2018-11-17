import datetime
import time
from threading import Thread
from time import sleep


class TaskTimer:
    __instance = None

    def __new__(cls, *args, **kwargs):
        """singleton"""
        if not cls.__instance:
            cls.__instance = object.__new__(cls)
        return cls.__instance

    def __init__(self):
        if not hasattr(self, 'task_queue'):
            setattr(self, 'task_queue', [])

        if not hasattr(self, 'is_running'):
            setattr(self, 'is_running', False)

    def write_log(self, level, msg):
        cur_time = datetime.datetime.now()
        s = "[" + str(cur_time) + "][" + level + "]   " + msg
        print(s)

    def work(self):

        """"""
        while True:
            for task in self.task_queue:
                if task['interval']:
                    self.cycle_task(task)
                elif task['timing']:
                    self.timing_task(task)

            sleep(5)

    def cycle_task(self, task):
        """"""
        if task['next_sec'] <= int(time.time()):
            try:
                task['fun'](*task['arg'])
                self.write_log("Normal","cycle task:" + task['fun'].__name__ + "Done")
            except Exception as e:
                self.write_log("UnNormal", "cycle task:" + task['fun'].__name__ + "Function inner Exception:" + str(e))
            finally:
                task['next_sec'] = int(time.time()) + task['interval']

    def timing_task(self, task):
        """"""

        today_sec = self.get_today_until_now()

        # second day, reset task
        if task['today'] != self.get_today():
            task['today'] = self.get_today()
            task['today_done'] = False

        if task['first_work']:
            if today_sec >= task['task_sec']:
                task['today_done'] = True
                task['first_work'] = False
            else:
                task['first_work'] = False

        # today not execute
        if not task['today_done']:
            if today_sec >= task['task_sec']: 
                try:
                    task['fun'](*task['arg'])
                    self.write_log("Noraml", "timing task:" + task['fun'].__name__ + "Done")
                except Exception as e:
                    self.write_log("Unnormal", "timing task:" + task['fun'].__name__ + "Function inner Exception:" + str(e))
                finally:
                    task['today_done'] = True
                    if task['first_work']:
                        task['first_work'] = False

    def get_today_until_now(self):
        """"""
        i = datetime.datetime.now()
        return i.hour * 3600 + i.minute * 60 + i.second

    def get_today(self):
        """"""
        i = datetime.datetime.now()
        return i.day

    def join_task(self, fun, arg, interval=None, timing=None):
        """
        interval,timing, only select one
        :param fun:
        :param arg: fun arg
        :param interval:
        :param timing:[0,24)
        """

        if (interval != None and timing != None) or (interval == None and timing == None):
            raise Exception('interval and timing can only select one')

        if timing and not 0 <= timing < 24:
            raise Exception('timing must be in [0,24)')

        if interval and interval < 5:
            raise Exception('interval at least 5')

        task = {
            'fun': fun,
            'arg': arg,
            'interval': interval,
            'timing': timing,
        }

        if timing:
            task['task_sec'] = timing * 3600
            task['today_done'] = False
            task['first_work'] = True
            task['today'] = self.get_today()
        elif interval:
            task['next_sec'] = int(time.time()) + interval

        self.task_queue.append(task)

        self.write_log("Normal", "add task:" + fun.__name__)

    def start(self):
        """"""
        if not self.is_running:
            thread = Thread(target=self.work)

            thread.start()

            self.is_running = True

            self.write_log("Normal", "TaskTimer run")

            return thread.ident

        self.write_log("Warning", "TaskTimer already run,Do not restart agarin!")
