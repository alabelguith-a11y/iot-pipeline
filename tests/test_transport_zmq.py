import threading
import unittest

try:
    import zmq  # noqa: F401
    HAVE_ZMQ = True
except ImportError:
    HAVE_ZMQ = False


@unittest.skipUnless(HAVE_ZMQ, "pyzmq not installed")
class ZmqTransportTests(unittest.TestCase):
    def test_roundtrip(self):
        from iotpipe import transport
        from iotpipe.config import load

        s = load(profile="test", zmq_endpoint="tcp://127.0.0.1:5599")
        stop, got = threading.Event(), []

        def consume():
            for m in transport.messages(s, stop, tick=0.1):
                if m:
                    got.append(m)
                    stop.set()

        t = threading.Thread(target=consume)
        t.start()
        pub = transport.make_publisher(s)
        for _ in range(20):  # PUB/SUB drops early messages; retry until the subscriber got one
            pub.publish("sensors/esp32-01/reading", b'{"hello": 1}')
            if got:
                break
            stop.wait(0.1)
        pub.close()
        t.join(timeout=5)
        self.assertEqual(got[0], ("sensors/esp32-01/reading", b'{"hello": 1}'))
