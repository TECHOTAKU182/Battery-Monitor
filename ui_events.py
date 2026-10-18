"""阻塞等待的 Tk 消息桥；原生窗口回调只入队，不重入 Tcl。"""
import queue
import threading
import tkinter as tk


class UiEvents:
    EVENT = '<<BatteryCommands>>'

    def __init__(self, root, callback):
        self.root = root
        self.queue = queue.SimpleQueue()
        self.wake = threading.Event()
        self.stopped = threading.Event()
        self.thread = None
        root.bind(self.EVENT, lambda _event: callback(), add='+')
        root.after_idle(self.start)

    def start(self):
        if self.stopped.is_set() or self.thread is not None:
            return
        self.thread = threading.Thread(target=self.relay, name='battery-ui-events', daemon=True)
        self.thread.start()

    def put(self, command):
        if not self.stopped.is_set():
            self.queue.put(command)
            self.wake.set()

    def get_nowait(self):
        return self.queue.get_nowait()

    def relay(self):
        while True:
            self.wake.wait()
            self.wake.clear()
            if self.stopped.is_set():
                return
            try:
                # threaded Tcl 将工作线程的调用投递至主事件循环；
                # 不能在原生 WndProc 中直接调用 Tk。
                self.root.event_generate(self.EVENT, when='tail')
            except (tk.TclError, RuntimeError):
                self.stopped.set()
                return

    def close(self):
        self.stopped.set()
        self.wake.set()
