from threading import Condition
from contextlib import contextmanager
import ldap


class LDAPPool(object):
    __shared_state = {}

    def __init__(self, connection_limit=8):
        self.__dict__ = self.__shared_state

        if 'lock' not in self.__dict__:
            self.lock = Condition()

        if 'connections' not in self.__dict__:
            self.connections = {}

        if 'connection_limit' not in self.__dict__:
            self.connection_limit = connection_limit

    def _create_connection(self, uri, dn, password):
        conn = ldap.initialize(uri)
        conn.simple_bind_s(dn, password)
        return conn

    @contextmanager
    def connection(self, uri, dn, password):
        # Get data for uri
        with self.lock:
            if uri not in self.connections:
                self.connections[uri] = Condition(), {}
            lock, connections = self.connections[uri]

        # Get data for dn
        with lock:
            if dn not in connections:
                connections[dn] = Condition(), [0], []
            lock, counter, connections = connections[dn]

        # Acquire or create a connection
        with lock:
            if connections:
                # Connection from pool
                conn = connections.pop()
            elif counter[0] < self.connection_limit:
                # No available, but below connection limit
                conn = self._create_connection(uri, dn, password)
                counter[0] += 1
            else:
                # Must wait for connection
                lock.wait()
                if connections:
                    # (Expected) a connection is available
                    conn = connections.pop()
                else:
                    # We were notified, but no connection: create new one
                    conn = self._create_connection(uri, dn, password)
                    counter[0] += 1

        # From this point, we MUST free one waiter with notify.
        try:
            try:
                conn.whoami_s()
            except ldap.SERVER_DOWN:
                conn = None
            except ldap.LDAPError:
                # Could report error here
                try:
                    conn.unbind_s()
                finally:
                    conn = None

            if conn is None:
                # We lost connection, reconnect
                conn = self._create_connection(uri, dn, password)
                # if reconnect fails, conn == None in the finally block

            # OK, we got a connection. Let's go!
            yield conn
        finally:
            with lock:
                if conn is not None:
                    connections.append(conn)
                else:
                    counter[0] -= 1
                lock.notify()
