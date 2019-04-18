from time import sleep
from traceback import format_exc
from queue import Queue
from select import select
from ssl import wrap_socket, CERT_REQUIRED, SSLWantReadError
from socket import (
    socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR, SO_REUSEPORT
)
from threading import Thread

from LibreCisco.peer.entity.peer_info import PeerInfo
from LibreCisco.peer.command import (
    HelpCmd, JoinCmd, SendCmd, ListCmd, LeaveNetCmd
)
from LibreCisco.peer.communication import (
    JoinHandler, CheckJoinHandler, AckNewMemberHandler, NewMemberHandler,
    MessageHandler, DisconnectHandler
)
from LibreCisco.peer.monitor import Monitor
from LibreCisco.utils.communication import Packet
from LibreCisco.utils.manager import ThreadManager
from LibreCisco.utils import printText, host_valid


class Peer(ThreadManager):
    """
    Attributes:
        server_info: A PeerInfo object represents this peer's peer info.
        pkt_handlers: A dict with str key and Handler value, which contains all
            handlers which this peer have ability to process.
        peer_pool: A dict with tuple key with (str, int) type and PeerInfo type
            , which contains all peers currently available in net.
    """

    @property
    def connectlist(self):
        return self.peer_pool.values()

    @property
    def _hash(self):
        return self.__hash

    def __init__(self, host, name, role, cert, _hash, loop_delay=1,
                 output_field=None):
        """Init of PeerManager
        Args:
            host: A tuple with (str, int) type, represents binding host.
            name: A string represents this peer's name in net.
            role: A string represents this peer's role in net.
            cert: A tuple with (str, str) type, the cert file's path.
            _hash: A str which is program self hash to send to packet.
            loop_delay: A int controls while loop delay.
        """
        super(Peer, self).__init__(
            loopDelay=loop_delay, output_field=output_field,
            auto_register=True)
        self.__send_queue = {}
        self.__in_fds = []
        self.__out_fds = []
        self.__ex_fds = []
        self.__pend_rm_fds = []

        self.__cert = cert
        self.__hash = _hash

        printText('Program hash: {{{}...{}}}'.format(
            self.__hash[:6], self.__hash[-6:]))
        self.server_info = PeerInfo(host=host, name=name, role=role)
        self.__tcp_server = self.__bind_socket(cert=self.__cert)

        self.peer_pool = {}
        self.pkt_handlers = {}
        self.commands = {}

        self.monitor = Monitor(peer=self)

    def start(self):
        super(Peer, self).start()
        self.monitor.start()

    def stop(self):
        for _, value in self.__send_queue.items():
            if value.empty() is False:
                sleep(2)
                return self.stop()

        self.__in_fds.remove(self.__tcp_server)
        handler = self.select_handler(pkt_type=DisconnectHandler.pkt_type)
        for each in self.peer_pool.values():
            if each.conn is None:
                continue
            pkt = handler.on_send(target=each.host)
            self.pend_packet(sock=each.conn, pkt=pkt)
        self.peer_pool = {}

        super(Peer, self).stop()
        self.monitor.stop()

    def run(self):
        self.__in_fds.append(self.__tcp_server)
        while (self.stopped.wait(self.loopDelay) is False or
               self.__send_queue != {}):
            readable, writable, exceptional = select(
                self.__in_fds, self.__out_fds, self.__ex_fds, 0)
            for sock in readable:
                if sock is self.__tcp_server:
                    conn, _ = sock.accept()
                    sock = conn
                self.__on_recv(sock=sock)
                # t = Thread(target=self.__on_recv, args=(sock.recv(4096)))
                # t.start()

            for sock in writable:
                if sock in self.__send_queue:
                    self.__on_send(sock=sock)
                    # t = Thread(target=self.__on_send, args=(sock))
                    # t.start()

            for sock in exceptional:
                pass

            self.__on_fds_rm()
        self.__tcp_server.close()
        sleep(2)
        printText('{} stopped.'.format(self.server_info))

    def new_tcp_long_conn(self, dst):
        assert host_valid(dst) is True
        unwrap_socket = socket(AF_INET, SOCK_STREAM)
        sock = wrap_socket(unwrap_socket, cert_reqs=CERT_REQUIRED,
                           ca_certs=self.__cert[0])
        sock.connect(dst)
        sock.setblocking(False)
        return sock

    def pend_socket(self, sock):
        self.__send_queue[sock] = Queue()
        self.__in_fds.append(sock)
        self.__out_fds.append(sock)

    def pend_socket_to_rm(self, sock):
        self.__pend_rm_fds.append(sock)
        self.__send_queue[sock].queue.clear()

    def pend_packet(self, sock, pkt, **kwargs):
        """Pending pkt's raw_data to queue's with sepecific sock.
        Any exception when wrapping handler to packet whould cause this connec-
        tion been close and thread maintaining loop terminate.

        Args:
            sock: A socket which want to pend on its queue.
            pkt: A Packet object ready to be pend.
            kwargs: Any additional arguments needs by handler object.
        """
        try:
            assert type(pkt) is Packet
            self.__send_queue[sock].put_nowait(pkt)
        except Exception:
            printText(format_exc())

    def select_handler(self, pkt_type):
        if pkt_type in self.pkt_handlers:
            return self.pkt_handlers[pkt_type]
        elif (pkt_type in self.monitor.handler):
            return self.monitor.handler[pkt_type]
        return None

    def add_peer_in_net(self, peer_info):
        if type(peer_info) is PeerInfo:
            self.peer_pool[peer_info.host] = peer_info
        else:
            raise ValueError('Parameter peer_info is not a PeerInfo object')

    def del_peer_in_net(self, peer_info):
        if peer_info.host in self.peer_pool:
            del self.peer_pool[peer_info.host]
            return True
        else:
            return False

    def is_peer_in_net(self, info):
        """Return if in current net pool
        Args:
            info: A PeerInfo object or a tuple with (str, int) type represents
                host.
        Returns:
            true if in net, or False.
        raise:
            ValueError: If peer_info's type is not PeerInfo or tuple (str, int)
        """
        if type(info) is tuple:
            return info in self.peer_pool
        elif type(info) is PeerInfo:
            return info.host in self.peer_pool
        else:
            raise ValueError('Parameter peer_info should be tuple with '
                             '(str, int) or type PeerInfo')

    def registerHandler(self):
        return self.__register_handler()

    def handler_unicast_packet(self, host, pkt_type, **kwargs):
        assert host_valid(host) is True
        handler = self.select_handler(pkt_type=pkt_type)
        if handler is None:
            printText('Unknow handler pkt_type')
        elif self.is_peer_in_net(info=host):
            peer_info = self.peer_pool[host]
            pkt = handler.on_send(target=host, **kwargs)
            self.pend_packet(sock=peer_info.conn, pkt=pkt)
        else:
            printText('Host not in current net.')

    def handler_broadcast_packet(self, host, pkt_type, **kwargs):
        handler = self.select_handler(pkt_type=pkt_type)
        if handler is None:
            printText('Unknow handler pkt_type')
        else:
            for (_, value) in self.peer_pool.items():
                if host[1] == 'all' or host[1] == value.role:
                    pkt = handler.on_send(target=value.host, **kwargs)
                    self.pend_packet(sock=value.conn, pkt=pkt)

    def registerCommand(self):
        return self.__register_command()

    def onProcess(self, msg_arr, **kwargs):
        return self.__on_command(msg_arr, **kwargs)

    def __on_command(self, msg_arr, **kwargs):
        msg_key = msg_arr[0].lower()
        msg_arr = msg_arr[1:]
        if msg_key in self.commands:
            return self.commands[msg_key].onProcess(msg_arr)
        return ''

    def __on_recv(self, sock):
        try:
            raw_data = sock.recv(4096)
            if raw_data == b'':
                return
            pkt = Packet.deserilize(raw_data=raw_data)
            handler = self.select_handler(pkt_type=pkt._type)

            if handler is None:
                printText('Unknown packet type: {}'.format(pkt._type))
            elif pkt._hash != self.__hash and pkt.is_reject() is False:
                # Invalid hash -> Dangerous peer's pkt.
                printText('Illegal peer {} with unmatch hash {{{}...{}}} try '
                          'to connect to net.'.format(
                              pkt.src, pkt._hash[:6], pkt._hash[-6:]))
                pkt.redirect_to_host(src=self.server_info.host, dst=pkt.src)
                pkt.set_reject(reject_data='Unmatching peer hash.')
                self.pend_socket(sock=sock)
                self.pend_packet(sock=sock, pkt=pkt)
            else:
                in_net = self.is_peer_in_net(info=pkt.src)
                if in_net is True or type(handler) in [
                        JoinHandler, AckNewMemberHandler, CheckJoinHandler,
                        DisconnectHandler]:
                    # In_net or A join / check_join pkt send.
                    # The exception pkt will be process whether reject or not.
                    handler.on_recv(src=pkt.src, pkt=pkt, sock=sock)
                    self.monitor.on_recv_pkt(addr=pkt.src, pkt=pkt, conn=sock)
                else:  # Not in net and not exception pkt
                    pkt.set_reject(reject_data='Not in current net.')
                    self.pend_packet(sock=sock, pkt=pkt)
        except SSLWantReadError:
            return
        except Exception:
            print(str(self.server_info) + format_exc())

    def __on_send(self, sock):
        try:
            q = self.__send_queue[sock]
            while q.empty() is False:
                pkt = q.get_nowait()
                data = Packet.serilize(obj=pkt)
                sock.send(data)
                if pkt._type == DisconnectHandler.pkt_type or pkt.is_reject():
                    self.pend_socket_to_rm(sock)
        except Exception:
            print(format_exc())

    def __on_fds_rm(self):
        if len(self.__pend_rm_fds) == 0:
            return
        for each in list(self.__pend_rm_fds):
            del self.__send_queue[each]
            self.__in_fds.remove(each)
            self.__out_fds.remove(each)
            if each in self.__ex_fds:
                self.__ex_fds.remove(each)
            each.close()
        self.__pend_rm_fds.clear()

    def __bind_socket(self, cert):
        unwrap_socket = socket(AF_INET, SOCK_STREAM)
        unwrap_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        unwrap_socket.setsockopt(SOL_SOCKET, SO_REUSEPORT, 1)
        unwrap_socket.bind(self.server_info.host)
        unwrap_socket.listen(5)
        unwrap_socket.setblocking(False)

        printText('Peer prepared')
        printText('This peer is running with certificate at path {}'.format(
                    cert[0]))
        printText('Please make sure other peers have same certicate.')
        return wrap_socket(unwrap_socket, certfile=cert[0], keyfile=cert[1],
                           server_side=True)

    def __register_handler(self):
        installing_handlers = [
            JoinHandler(self), CheckJoinHandler(self), NewMemberHandler(self),
            MessageHandler(self), AckNewMemberHandler(self),
            DisconnectHandler(self)
        ]
        for each in installing_handlers:
            self.pkt_handlers[type(each).pkt_type] = each

    def __register_command(self):
        self.commands = {
            'help': HelpCmd(self),
            'join': JoinCmd(self),
            'send': SendCmd(self),
            'list': ListCmd(self),
            'leavenet': LeaveNetCmd(self)
        }
