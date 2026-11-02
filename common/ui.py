"""Bounded main-thread work dispatch with replacement of stale visual updates."""
from collections import OrderedDict, deque
import threading
import time


class UiDispatcher:
    def __init__(self, capacity=512):
        self.capacity=capacity
        self.queue=deque()
        self.latest=OrderedDict()
        self.lock=threading.Lock()

    def post(self, fn, *args, key=None, **kwargs):
        item=(fn,args,kwargs)
        with self.lock:
            if key is not None:
                self.latest[key]=item
            elif len(self.queue)<self.capacity:
                self.queue.append(item)
            else:
                return False
        return True

    def drain(self, budget_ms=4, max_items=64):
        deadline=time.perf_counter()+budget_ms/1000
        count=0
        while count<max_items and time.perf_counter()<deadline:
            with self.lock:
                if self.queue: item=self.queue.popleft()
                elif self.latest: _,item=self.latest.popitem(last=False)
                else: break
            fn,args,kwargs=item
            try: fn(*args,**kwargs)
            except Exception as exc: print(f'[UI] {exc}')
            count+=1
        return count

    def pending(self):
        with self.lock: return bool(self.queue or self.latest)
