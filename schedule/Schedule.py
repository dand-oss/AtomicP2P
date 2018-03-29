import traceback, time
from croniter import croniter
from threading import Event
from datetime import datetime, timedelta

from utils.Explainer import ScriptExplainer
from utils.Enums import LogLevel
from utils.Manager import ThreadManager

class Type:

    def __init__(self, json):
        if 'text' in json:
            self.mode = 'text'
        elif 'count' in json:
            self.mode = 'count'
            self.time = json['count']
            self.TS = json['startTS'] if 'startTS' in json else time.time()
        elif 'cron' in json:
            self.mode = 'cron'
            self.time = json['cron']

class Schedule(ThreadManager):

    def __init__(self, manager, outputQueue, json):
        try:
            ThreadManager.__init__(self, 'Schedule/%s' % json['name'], outputQueue)
            self.manager = manager
            self.name = 'Schedule/%s' % json['name']
            self.target = json['target']
            self.type = Type(json['type'])
            self.beforeScript = json['beforeScript']
            self.script = json['script']
            self.nextSchedule = self.manager.getScheduleByName(json['nextSchedule'])
            self.sleep = 0
            self.lastRun = 0
            self.print('Inited.', LogLevel.SUCCESS)
        except KeyError as keyErr:
            self.print('Init schedule failed: KeyError with missing %s' % keyErr, LogLevel.WARNING)
        except:
            traceback.print_exc()

    def calSleep(self):
        if self.type.mode == 'count':
            return self.type.time - int((time.time() - self.type.TS) % self.type.time)
        elif self.type.mode == 'cron':
            return (croniter(self.type.time, datetime.now()).get_next(datetime) - datetime.now()).total_seconds()
        else:
            return 5

    def update(self, json):
        try:
            self.name = 'Schedule/%s' % json['name']
            self.target = json['target']
            self.type = Type(json['type'])
            self.beforeScript = json['beforeScript']
            self.script = json['script']
            self.nextSchedule = self.manager.getScheduleByName(json['nextSchedule'])
            self.print('Updated.', LogLevel.SUCCESS)
        except KeyError as keyErr:
            self.print('Update schedule failed: KeyError with missing %s' % keyErr, LogLevel.WARNING)
        except:
            traceback.print_exc()

    def exit(self):
        del self.manager.schedules[self.name[9:]]
        self.name = '%s(Exited)' % self.name
        super(Schedule, self).exit()

    def start(self):
        if self.type.mode == 'text':
            self.sleep = 5
        else:
            self.sleep = self.calSleep()
        super(Schedule, self).start()
        self.print('%s started.' % self.name)

    def run(self):
        while not self.stopped.wait(self.sleep):
            if self.isExit():
                break
            self.lastRun = time.time()
            self.print('TEST')
            self.sleep = self.calSleep()
            if self.type.mode == 'text':
                self.exit()

    def info(self):
        return "%s ,last run at %d" % (self, self.lastRun)

class NextSchedule:
    
    def __init__(self, json):
        self.command = json['command']
        self.delay = int(json['delay']) if 'delay' in json else 0
        self.nextSchedule = json['nextSchedule']

    def run(self):
        time.sleep(self.delay)
        for each in self.command:
            exec(each)
