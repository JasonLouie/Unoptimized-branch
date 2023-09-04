# Final implementation of chatserver with audio and video streaming as well as text messaging
import threading, socket, time

# socket.gethostbyname(socket.gethostname())
# The above line of code receives the ipv4 address of the client that this program is running on.
# I had to change it to 192.168.1.171 since the line of code above started returning the wrong ipv4 address
# This assumes that the server is being ran on my computer.
host = '192.168.1.171'
chatPort = 55555
videoPort = 55666
audioPort = 55777
buffer_size = 65536

class User:
    def __init__(self, name="", text_socket=socket.socket()):
        self.username = name
        self.text_socket = text_socket
        self.audio_socket = socket.socket()
        self.address = ""
        self.audioValid = True
    
    def setUsername(self, username: str):
        self.username = username
    
    def setAddress(self, addr):
        self.address = addr
    
    def setAudioSocket(self, audioSocket):
        self.audio_socket = audioSocket

    def getUsername(self)->str:
        return self.username
    
    def getAddress(self)->str:
        return self.address
    
    def canHear(self)->bool:
        return self.audioValid
    
    def sendText(self, data: bytes):
        self.text_socket.send(data)
    
    def sendAudio(self, data: bytes):
        self.audio_socket.send(data)
    
    def endAudio(self):
        self.audio_socket.close()
    
    def endText(self):
        # If text chat ends, audio chat must end as well. This informs server to break the
        # handleAudio thread for the user
        self.audioValid = False
        self.text_socket.close()

class Server:
    def __init__(self):
        # TCP socket for text message server
        self.text_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # TCP Socket for audio streaming server
        self.audio_server = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        # UDP socket for video streaming server
        self.video_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.runThread = True
        # List of clients in the server
        self.clients = []
    
    # Start server
    def start(self):
        print(f"Listening for connections at {host}...")
        self.text_server.bind((host,chatPort))
        self.text_server.listen()

        self.audio_server.bind((host,audioPort))
        self.audio_server.listen()

        # Change buffer size for UDP socket so that the particular resolution of jpg packets can be sent
        self.video_server.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, buffer_size)
        self.video_server.bind((host, videoPort))

        # Handle packets of data for receiving video stream within the UDP Server
        handleVideo_thread = threading.Thread(target=self.videoReceive, daemon=True)
        handleVideo_thread.start()

        # Handle packets of data for receiving audio stream
        handleAudio_thread = threading.Thread(target=self.receiveAudio, daemon=True)
        handleAudio_thread.start()

        # Create a thread for accepting users into the text chat server
        handleChatJoin_thread = threading.Thread(target=self.receive, daemon=True)
        handleChatJoin_thread.start()

        self.checkForExit()
    
    # Wait for user input on the server-side and use this as a way to shutdown the server
    # This works because the only line of code running on the main thread is the input command and after
    # there is input, the server will shutdown. Since all the other threads are daemon threads, they will
    # also terminate as soon as the main thread ends.
    def checkForExit(self):
        while True:
            try:
                input("Enter Ctrl + C to shutdown server\n")
            except KeyboardInterrupt:
                self.runThread = False
                self.shutdown()
                break

    # Function for handling user ping
    def writeRecvPing(self, ping: float)->str:
        now = time.time()
        return f"Ping: {((now-ping)*1000):.2f}"

    # Check for repeated usernames
    # Returns false if the username is not taken and true if it is taken
    def takenUsername(self, username: str)->bool:
        # Check all clients and if name is not taken then return false
        for client in self.clients:
            if client.getUsername() == username:
                return True
        return False
    
    # Function used for obtaining valid username from user
    def getValidUsername(self, user: socket.socket)->str:
        username = user.recv(1024).decode('ascii')
        while self.takenUsername(username):
            user.send("#TAKEN#".encode('ascii'))
            username = user.recv(1024).decode('ascii')
        user.send("Connected to the server!".encode('ascii'))
        return username

    # Shutdown server
    def shutdown(self):
        print("Shutting Down...")
        self.broadcast("#CLOSING#".encode('ascii'), allClients=True)
        self.text_server.close()
        self.video_server.close()
        self.audio_server.close()

    # Functionalities:
    # Send a message to all but sender
    # Send messages to all valid clients
    # Send messages to ALL clients (even the clients in the middle of entering username)
    def broadcast(self, message: bytes, sender = "", allClients = False):
        for client in self.clients:
            if (client.getUsername() != sender and client.getUsername()) or allClients:
                try:
                    client.sendText(message)
                except:
                    client.endText()
                    self.clients.remove(client)
    
    # Find a particular client from their username
    def findClient(self, username: str)->User:
        for client in self.clients:
            if username == client.getUsername():
                return client
        # Return a null client if the client does not exist
        return User("",socket.socket())

    # Send video to all clients but the sender
    def broadcastVideo(self, addr: str, packet: bytes, numClients=2):
        # No need to send video if there is only one client in the server
        if len(self.clients) >= numClients:
            for client in self.clients:
                if client.getAddress() != addr and client.getAddress() != "":
                    self.video_server.sendto(packet, client.getAddress())
    
    # Function for handling a new user in TCP chat server
    def handle(self, user: User, userSocket: socket.socket):
        # Attempt to assign a username to a new user
        try:
            user.sendText("#NAME#".encode('ascii'))
            username = self.getValidUsername(userSocket)
            user.setUsername(username)
            print(f"Username of the client is {username}!")
            self.broadcast(f'{username} joined the chat!'.encode('ascii'), sender=username)
        # If a nickname was not received by the server, they disconnected before entering a username
        except:
            print("User disconnected before entering a username")
            user.endText()
            return

        # Manage sending and receiving messages from a specific user
        while self.runThread:
            try:
                message = userSocket.recv(1024)
                if message[0:6].decode('ascii') == "#PING:":
                    ping = self.writeRecvPing(float(message[6:]))
                    user.sendText(f"T-{ping}".encode('ascii'))
                else:
                    self.broadcast(message, sender=username)
            # Remove the client that sends a failed message
            # This is when the client terminates its socket, thus terminating its connection to the server
            except:
                self.clients.remove(user)
                user.endText()
                self.broadcast(f"{username} left the chat!".encode('ascii'))
                print(f"{username} left the chat!")
                break
    
    # Function for accepting new clients into the TCP text server
    def receive(self):
        while self.runThread:
            try:
                socket, address = self.text_server.accept()
                print(f"Connected with {str(address)}")
                newUser = User("", socket)
                self.clients.append(newUser)
                handleUserChat_thread = threading.Thread(target=self.handle, args=(newUser,socket,), daemon=True)
                handleUserChat_thread.start()
            except:
                break
    
    # Handle users joining server
    def receiveAudio(self):
        while self.runThread:
            try:
                socket, address = self.audio_server.accept()
                print(f"Connected to audio server with {str(address)}")
                handleAudio_thread = threading.Thread(target=self.handleAudio, args=(socket,), daemon=True)
                handleAudio_thread.start()
            except:
                break

    # Function that handles receiving data within the UDP server for video streaming
    # Called through the creation of a thread. It must be able to handle all of the specific conditions
    # such as updating a user on the server's side with their specific return address.
    # The socket function recvfrom simply receives data and cannot choose to receive data from a particular sender.
    # What I mean by this is that recvfrom returns two parameters: data and sender's return address, but the server has no way of
    # ensuring that a specific client is sending data to the server. Because of this, only one videoReceive thread is required
    # while TCP requires every client to have its own handling thread for receiving data.
    def videoReceive(self):
        while self.runThread:
            try:
                packet,addr = self.video_server.recvfrom(buffer_size)
                # Check whether the packet is a string (decodable in ascii?)
                try:
                    msg = packet.decode('ascii')
                    # Update address of client for streaming video (this return address is used to send video data)
                    if msg[0:6] == "FIRST:":
                        client = self.findClient(msg[6:])
                        # If the client was found, update address
                        if client.getUsername():
                            client.setAddress(addr)
                    elif msg == "START":
                        self.broadcastVideo(addr, "#START#".encode('ascii'))
                    elif msg == "END":
                        self.broadcastVideo(addr, "#STOP#".encode('ascii'), 1)
                    elif msg[0:6] == "#PING:":
                        ping = self.writeRecvPing(float(msg[6:]))
                        self.video_server.sendto(f"V-{ping}".encode('ascii'),addr)
                        
                # If packet cannot be decoded with ascii it is encoded as jpg and can be sent to other clients
                except:
                    self.broadcastVideo(addr, packet)
            except:
                break
    
    # Send audio packets to all clients except sender
    def broadcastAudio(self, audio: bytes, sender: str):
        for client in self.clients:
            if client.getUsername() != sender:
                try:
                    client.sendAudio(audio)
                except Exception as e:
                    print(f"Audio sending error:\n{e}")
    
    # Handles audio from client
    def handleAudio(self, audioSocket: socket.socket):
        client = User()
        try:
            msg = audioSocket.recv(1024).decode('ascii')
            if msg[0:7] == "Joined:":
                # print("Updated audio socket")
                client = self.findClient(msg[7:])
                client.setAudioSocket(audioSocket)
                # Send connection verified to prompt ping updates
                audioSocket.send("#VERIFIED#".encode('ascii'))
        except:
            audioSocket.close()
            return

        while client.canHear():
            try:
                audio = audioSocket.recv(1024*8)
                try:
                    if audio[0:6].decode('ascii') == "#PING:":
                        ping = self.writeRecvPing(float(audio[6:]))
                        audioSocket.send(f"A-{ping}".encode('ascii'))
                except:
                    self.broadcastAudio(audio, msg[7:])
            except:
                # remove the client that sends a failed message
                client.endAudio()
                # print(f"{address} disconnected from audio server.")
                break
        
if __name__ == '__main__':
    server = Server()
    server.start()