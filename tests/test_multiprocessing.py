#!/usr/bin/python

from base_test import DakTestCase

from daklib.dakmultiprocessing import DakProcessPool, \
                                      PROC_STATUS_SUCCESS,   PROC_STATUS_MISCFAILURE, \
                                      PROC_STATUS_EXCEPTION, PROC_STATUS_SIGNALRAISED
import signal

def test_function(num, num2):
    from os import kill, getpid

    if num == 1:
        sigs = [signal.SIGTERM, signal.SIGPIPE, signal.SIGALRM, signal.SIGHUP]
        kill(getpid(), sigs[num2])

    if num2 == 3:
        raise Exception('Test uncaught exception handling')

    if num == 0 and num2 == 1:
        return (PROC_STATUS_MISCFAILURE, 'Test custom error return')

    return (PROC_STATUS_SUCCESS, 'blah, %d, %d' % (num, num2))

class DakProcessPoolTestCase(DakTestCase):
    def testPool(self):
        def alarm_handler(signum, frame):
            raise AssertionError('Timed out')

        # Shouldn't take us more than 15 seconds to run this test
        signal.signal(signal.SIGALRM, alarm_handler)
        signal.alarm(15)

        p = DakProcessPool()
        for s in range(3):
            for j in range(4):
                p.apply_async(test_function, [s, j])

        p.close()
        p.join()

        signal.alarm(0)
        signal.signal(signal.SIGALRM, signal.SIG_DFL)

        expected = [(PROC_STATUS_SUCCESS,      'blah, 0, 0'),
                    (PROC_STATUS_MISCFAILURE,  'Test custom error return'),
                    (PROC_STATUS_SUCCESS,      'blah, 0, 2'),
                    (PROC_STATUS_EXCEPTION,    'Test uncaught exception handling'),
                    (PROC_STATUS_SIGNALRAISED, 15),
                    (PROC_STATUS_SIGNALRAISED, 13),
                    (PROC_STATUS_SIGNALRAISED, 14),
                    (PROC_STATUS_SIGNALRAISED, 1),
                    (PROC_STATUS_SUCCESS,      'blah, 2, 0'),
                    (PROC_STATUS_SUCCESS,      'blah, 2, 1'),
                    (PROC_STATUS_SUCCESS,      'blah, 2, 2'),
                    (PROC_STATUS_EXCEPTION,    'Test uncaught exception handling')]

        self.assertEqual( len(p.results), len(expected) )

        for r in range(len(p.results)):
            self.assertEqual(p.results[r], expected[r])
