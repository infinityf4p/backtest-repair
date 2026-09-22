"""SSH password transport. Passwords stay in orchestrator memory, never in archives."""

import os
import time


def execute(config, command, payload=b"", timeout=120, log=None):
    import paramiko

    client = paramiko.SSHClient()
    client.load_host_keys(config["known_hosts"])
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    password = os.environ.get(config.get("password_env", "BTR_SSH_PASSWORD"))
    # Retry only before any command is sent; a dropped execution is never
    # silently counted as a successful native run or replayed for free.
    for attempt in range(2):
        try:
            client.connect(
                config["hostname"],
                port=config.get("port", 22),
                username=config["user"],
                password=password,
                key_filename=config.get("identity"),
                look_for_keys=False,
                allow_agent=False,
                timeout=15,
                banner_timeout=15,
                auth_timeout=15,
            )
            break
        except paramiko.AuthenticationException:
            client.close()
            raise
        except (OSError, paramiko.SSHException):
            client.close()
            if attempt:
                raise
            time.sleep(0.25)
    try:
        channel = client.get_transport().open_session(timeout=15)
        channel.settimeout(timeout)
        channel.exec_command(command)
        if payload:
            channel.sendall(payload)
        channel.shutdown_write()
        output, errors, start = [], [], time.monotonic()
        while True:
            if time.monotonic() - start > timeout:
                channel.close()
                raise TimeoutError("Remote Docker execution timed out")
            if channel.recv_ready():
                data = channel.recv(65536)
                output.append(data)
                if log:
                    log.write(data.decode("utf-8", "replace"))
                    log.flush()
            if channel.recv_stderr_ready():
                data = channel.recv_stderr(65536)
                errors.append(data)
                if log:
                    log.write(data.decode("utf-8", "replace"))
                    log.flush()
            if (
                (channel.eof_received or channel.closed)
                and channel.exit_status_ready()
                and not channel.recv_ready()
                and not channel.recv_stderr_ready()
            ):
                break
            time.sleep(0.025)
        return channel.recv_exit_status(), b"".join(output), b"".join(errors)
    finally:
        client.close()
