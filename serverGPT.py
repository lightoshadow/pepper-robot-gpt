""" 
server to be run on an external computer
this queries the openai api and sends answers back to the robot
"""

import threading
import time
import sys
import socket
import selectors
import types
import openai 
import json
import speech_recognition as sr
import sounddevice
import APIKey

r = sr.Recognizer()
mic = sr.Microphone()

client = openai.OpenAI()

model = "gpt-4o-mini"

class Agent:
    def __init__(self, client, model, background):
        self.client = client
        self.model = model
        self.messages = [{"role": "system", "content": background}]

    def queryAI(self,question):
        self.messages.append({"role": "user", "content": question})
        answer = client.chat.completions.create(model = self.model, messages = self.messages).choices[0].message.content
        self.messages.append({"role": "assistant", "content": answer})
        return answer

    def printMessages(self):
        print(len(self.messages), self.messages)


with open('background.txt') as f:
    background = f.read()

with open("backgroundActions.txt") as f:
    backgroundActions = f.read()

answerAI = Agent(client, model, background)
actionsAI = Agent(client, model, backgroundActions)
sel = selectors.DefaultSelector()
print(sys.argv)
host, port = sys.argv[1], int(sys.argv[2])
lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # permette il riutilizzo del socket dopo la chiusura
lsock.bind((host, port))
lsock.listen()
print(f"Listening on {(host, port)}")
lsock.setblocking(False)
sel.register(lsock, selectors.EVENT_READ, data=None)

connections = []

def accept_wrapper(sock):
    try:
        conn, addr = sock.accept()  # Should be ready to read
    except socket.error as e:
        print(f"Error accepting connection: {e}")
        return
    print(f"Accepted connection from {addr}")
    conn.setblocking(False)
    data = types.SimpleNamespace(addr=addr, inb=b"", outb=b"")
    events = selectors.EVENT_READ | selectors.EVENT_WRITE
    sel.register(conn, events, data=data)
    connections.append(conn)

def service_connection(key, mask):
    sock = key.fileobj
    data = key.data
    try:
        if mask & selectors.EVENT_READ:
            recv_data = sock.recv(1024)
            if recv_data:
                data.outb += recv_data
            else:
                print(f"Closing connection to {data.addr}")
                sel.unregister(sock)
                sock.close()
                connections.remove(sock)
        if mask & selectors.EVENT_WRITE:
            if data.outb.decode() == "ready":
                print("ricevuto ready")
                #userInput = input(">>>>")
                
                with mic as source:
                    r.adjust_for_ambient_noise(source)
                    print("parla")
                    audio = r.listen(source)
                    responseRec = r.recognize_google(audio, language="it-IT")
                    print("mic = ",responseRec)
                    userInput = responseRec
                
                action = actionsAI.queryAI(userInput)
                answer = answerAI.queryAI(userInput)
                response = {"action":action,"answer":answer}
                
                print("risposta = ", str(response))
                try:
                    sent = sock.send(bytes(json.dumps(response), encoding = "utf-8"))  # Should be ready to write
                except socket.error as e:
                    print(f"Error sending data to {data.addr}: {e}")
                    sel.unregister(sock)
                    sock.close()
                    connections.remove(sock)
                else:
                    data.outb = data.outb[sent:]
    except socket.error as e:
        print(f"Error handling connection to {data.addr}: {e}")
        #sel.unregister(sock)
        #sock.close()
        #connections.remove(sock)

try:
    while True:
        events = sel.select(timeout=None)
        for key, mask in events:
            if key.data is None:
                accept_wrapper(key.fileobj)
            else:
                service_connection(key, mask)
except KeyboardInterrupt:
    print("Caught keyboard interrupt, exiting")
except Exception as e:
    print(f"Caught exception: {e}")
finally:
    sel.close() 

