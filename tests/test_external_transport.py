"""Regression: SSH exit status must not truncate a result still arriving in chunks."""
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from backtest_repair.remote import execute

def test_exit_status_before_eof_does_not_truncate(monkeypatch):
    import paramiko
    chunks=[b'a'*65536,b'b'*65536,b'c'*12345]
    expected=b''.join(chunks)
    class Channel:
        closed=False
        next_at=0
        @property
        def eof_received(self): return not chunks
        def settimeout(self,_): pass
        def exec_command(self,_): pass
        def shutdown_write(self): pass
        def recv_ready(self): return bool(chunks) and time.monotonic()>=self.next_at
        def recv(self,_):
            self.next_at=time.monotonic()+0.04
            return chunks.pop(0)
        def recv_stderr_ready(self): return False
        def exit_status_ready(self): return True
        def recv_exit_status(self): return 0
    channel=Channel()
    class Client:
        def load_host_keys(self,_): pass
        def set_missing_host_key_policy(self,_): pass
        def connect(self,*args,**kwargs): pass
        def close(self): pass
        def get_transport(self): return self
        def open_session(self,**kwargs): return channel
    monkeypatch.setattr(paramiko,'SSHClient',Client)
    code,out,err=execute({'known_hosts':'unused','hostname':'unused','user':'unused'},'unused',timeout=2)
    assert code==0 and out==expected and err==b''
