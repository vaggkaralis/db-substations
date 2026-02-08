class Clock:
    @staticmethod
    def schedule_once(fn, timeout=0):
        try:
            fn(None)
        except TypeError:
            fn()
