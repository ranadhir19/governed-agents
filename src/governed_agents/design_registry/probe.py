"""Reachability measured, not assumed.

A network probe tests the endpoints a design handoff depends on and
reports per-endpoint reachable/blocked with evidence. It establishes
reachability only: no credentials are ever sent, and no application
payload is exchanged.

Evidence distinguishes, for example, a TLS handshake reset (possible
TLS-intercepting proxy that is not allow-listed) from a host that is
simply unreachable.
"""

import socket
import ssl
import time
from urllib.parse import urlparse

DEFAULT_TIMEOUT = 3.0


def _parse_endpoint(endpoint):
    """Accept 'host:port', 'http(s)://host[:port]/...' and return (host, port, use_tls)."""
    text = endpoint.strip()
    if "://" in text:
        parts = urlparse(text)
        host = parts.hostname or ""
        use_tls = parts.scheme.lower() == "https"
        port = parts.port or (443 if use_tls else 80)
    else:
        use_tls = False
        if text.startswith("["):
            # IPv6 literal [::1]:port
            host, _, port_text = text.rpartition("]:")
            host = host.lstrip("[")
        elif text.count(":") == 1:
            host, _, port_text = text.partition(":")
        else:
            host, port_text = text, ""
        port = int(port_text) if port_text else 80
    return host, port, use_tls


def probe_endpoint(endpoint, timeout=DEFAULT_TIMEOUT, tls=False):
    """Probe one endpoint. Returns a dict with status and evidence.

    status is 'reachable' or 'blocked'. tls=True additionally attempts
    a TLS handshake so handshake resets are classified separately.
    """
    started = time.monotonic()
    result = {
        "endpoint": endpoint,
        "status": "blocked",
        "evidence": "",
        "latency_ms": None,
    }
    try:
        host, port, use_tls = _parse_endpoint(endpoint)
    except (ValueError, AttributeError) as exc:
        result["evidence"] = "endpoint_parse_failed: %s" % exc
        return result
    if not host:
        result["evidence"] = "endpoint_parse_failed: empty host"
        return result

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        result["evidence"] = (
            "dns_resolution_failed (%s): host unreachable, name does not resolve"
            % exc
        )
        return result
    except OSError as exc:
        result["evidence"] = "address_lookup_failed: %s" % exc
        return result

    last_error = None
    for family, socktype, proto, _, sockaddr in infos:
        sock = None
        try:
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(timeout)
            sock.connect(sockaddr)
            if tls or use_tls:
                try:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    tls_sock = context.wrap_socket(sock, server_hostname=host)
                    tls_sock.do_handshake()
                    tls_sock.close()
                except ssl.SSLError as exc:
                    result["evidence"] = (
                        "tls_handshake_failed (%s): connection reached the host "
                        "but the TLS handshake was reset or rejected. Possible "
                        "TLS-intercepting proxy that is not allow-listed, or a "
                        "non-TLS service on this port." % exc
                    )
                    return result
            result["status"] = "reachable"
            result["evidence"] = "tcp_connect_succeeded%s" % (
                " + tls_handshake_succeeded" if (tls or use_tls) else ""
            )
            result["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            return result
        except socket.timeout:
            last_error = "connect_timeout: no response within %.1fs, likely firewall/proxy drop" % timeout
        except ConnectionRefusedError:
            last_error = (
                "connection_refused: host is up but the port is closed or filtered"
            )
        except OSError as exc:
            last_error = "connect_failed: %s" % exc
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
    result["evidence"] = last_error or "connect_failed: unknown error"
    return result


def probe_endpoints(endpoints, timeout=DEFAULT_TIMEOUT, tls=False):
    """Probe several endpoints; returns a list of result dicts."""
    return [probe_endpoint(ep, timeout=timeout, tls=tls) for ep in endpoints]
