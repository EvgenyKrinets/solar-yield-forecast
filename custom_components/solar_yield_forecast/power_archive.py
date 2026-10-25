"""Compact measured 15-minute history independent of Recorder purge settings."""
from math import isfinite
from .shape import power_hours


class PowerArchive:
    def __init__(self, data=None, now=0):
        self.bins={};self.pending=[];self.last_flush=0
        data=data if isinstance(data,dict) else {}
        for stamp,row in (data.get('bins') or {}).items():
            try:
                t=int(stamp);energy,coverage=map(float,row)
                if now-90*86400<=t<=now and isfinite(energy) and energy>=0 and 0<=coverage<=900:
                    self.bins[t]=[energy,coverage]
            except (ValueError,TypeError):
                continue
        for row in data.get('pending',[]):
            if not isinstance(row,(list,tuple)) or len(row)!=2:
                continue
            stamp,value=row
            if isinstance(stamp,(int,float)) and now-86400<=stamp<=now:
                self.pending.append((stamp,value if isinstance(value,(int,float)) and isfinite(value) and value>=0 else None))
        # A restart is an observation gap, not evidence that the old power
        # continued throughout downtime. A short bounded gap can later bridge.
        checkpoint=data.get('saved_until')
        if self.pending and isinstance(checkpoint,(int,float)) and self.pending[-1][0]<=checkpoint<now:
            self.pending.append((checkpoint,None))

    def observe(self, stamp, value):
        if value is not None and (not isfinite(value) or value<0):
            value=None
        self.pending.append((stamp,value))
        if stamp-self.last_flush>=60:
            self.flush(stamp)

    def flush(self, now):
        # Delay closure by the interpolation window so a short gap crossing
        # a quarter boundary can be filled before the quarter is archived.
        self.pending=sorted(dict(self.pending).items())
        for stamp,row in power_hours(self.pending,now,900).items():
            if now-90*86400<=stamp and stamp+900<=now-600:
                self.bins[int(stamp)]=row
        self.bins={t:r for t,r in self.bins.items() if t>=now-90*86400}
        older=[r for r in self.pending if r[0]<now-3600]
        self.pending=([(now-3600,older[-1][1])] if older else [])+[r for r in self.pending if r[0]>=now-3600]
        self.last_flush=now

    def merge_recorder(self, bins, now):
        for stamp,row in bins.items():
            if now-90*86400<=stamp and stamp+900<=now-600:
                # Recorder wins on equal quality; incomplete imports must not
                # erase a complete interval already saved before a purge.
                if row[1]>=self.bins.get(int(stamp),[0,0])[1]:
                    self.bins[int(stamp)]=list(row)

    def snapshot(self):
        return {'bins':{str(t):r for t,r in sorted(self.bins.items())},
                'pending':self.pending,'saved_until':self.last_flush}
