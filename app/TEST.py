
from time import sleep
import tellopy
import time
import sys
import pygame
import threading
import av
import cv2 as cv2 
import numpy
import traceback
import time
import sys
import tellopy
import pygame
import pygame.display
import pygame.key
import pygame.locals
import pygame.font
import os
import datetime
from subprocess import Popen, PIPE

prev_flight_data = None
video_player = None
video_recorder = None
font = None
wid = None
date_fmt = '%Y-%m-%d_%H%M%S'

def toggle_recording(drone, speed):
    global video_recorder
    global date_fmt
    if speed == 0:
        return

    if video_recorder:
        # already recording, so stop
        video_recorder.stdin.close()
        status_print('Video saved to %s' % video_recorder.video_filename)
        video_recorder = None
        return

    # start a new recording
    filename = '%s/Pictures/tello-%s.mp4' % (os.getenv('HOME'),
                                             datetime.datetime.now().strftime(date_fmt))
    video_recorder = Popen([
        'mencoder', '-', '-vc', 'x264', '-fps', '30', '-ovc', 'copy',
        '-of', 'lavf', '-lavfopts', 'format=mp4',
        # '-ffourcc', 'avc1',
        # '-really-quiet',
        '-o', filename,
    ], stdin=PIPE)
    video_recorder.video_filename = filename
    status_print('Recording video to %s' % filename)

def take_picture(drone, speed):
    if speed == 0:
        return
    drone.take_picture()

def palm_land(drone, speed):
    if speed == 0:
        return
    drone.palm_land()

def toggle_zoom(drone, speed):
    # In "video" mode the drone sends 1280x720 frames.
    # In "photo" mode it sends 2592x1936 (952x720) frames.
    # The video will always be centered in the window.
    # In photo mode, if we keep the window at 1280x720 that gives us ~160px on
    # each side for status information, which is ample.
    # Video mode is harder because then we need to abandon the 16:9 display size
    # if we want to put the HUD next to the video.
    if speed == 0:
        return
    drone.set_video_mode(not drone.zoom)
    pygame.display.get_surface().fill((0,0,0))
    pygame.display.flip()

controls = {
    'w': 'forward',
    's': 'backward',
    'a': 'left',
    'd': 'right',
    'space': 'up',
    'left shift': 'down',
    'right shift': 'down',
    'q': 'counter_clockwise',
    'e': 'clockwise',
    # arrow keys for fast turns and altitude adjustments
    'left': lambda drone, speed: drone.counter_clockwise(speed*2),
    'right': lambda drone, speed: drone.clockwise(speed*2),
    'up': lambda drone, speed: drone.up(speed*2),
    'down': lambda drone, speed: drone.down(speed*2),
    'tab': lambda drone, speed: drone.takeoff(),
    'backspace': lambda drone, speed: drone.land(),
    'p': palm_land,
    'r': toggle_recording,
    'z': toggle_zoom,
    'enter': take_picture,
    'return': take_picture,
}

class FlightDataDisplay(object):
    # previous flight data value and surface to overlay
    _value = None
    _surface = None
    # function (drone, data) => new value
    # default is lambda drone,data: getattr(data, self._key)
    _update = None
    def __init__(self, key, format, colour=(255,255,255), update=None):
        self._key = key
        self._format = format
        self._colour = colour

        if update:
            self._update = update
        else:
            self._update = lambda drone,data: getattr(data, self._key)

    def update(self, drone, data):
        new_value = self._update(drone, data)
        if self._value != new_value:
            self._value = new_value
            self._surface = font.render(self._format % (new_value,), True, self._colour)
        return self._surface

def flight_data_mode(drone, *args):
    return (drone.zoom and "VID" or "PIC")

def flight_data_recording(*args):
    return (video_recorder and "REC 00:00" or "")  # TODO: duration of recording

def update_hud(hud, drone, flight_data):
    (w,h) = (158,0) # width available on side of screen in 4:3 mode
    blits = []
    for element in hud:
        surface = element.update(drone, flight_data)
        if surface is None:
            continue
        blits += [(surface, (0, h))]
        # w = max(w, surface.get_width())
        h += surface.get_height()
    h += 64  # add some padding
    overlay = pygame.Surface((w, h), pygame.SRCALPHA)
    overlay.fill((0,0,0)) # remove for mplayer overlay mode
    for blit in blits:
        overlay.blit(*blit)
    pygame.display.get_surface().blit(overlay, (0,0))
    pygame.display.update(overlay.get_rect())

def status_print(text):
    pygame.display.set_caption(text)

hud = [
    FlightDataDisplay('height', 'ALT %3d'),
    FlightDataDisplay('ground_speed', 'SPD %3d'),
    FlightDataDisplay('battery_percentage', 'BAT %3d%%'),
    FlightDataDisplay('wifi_strength', 'NET %3d%%'),
    FlightDataDisplay(None, 'CAM %s', update=flight_data_mode),
    FlightDataDisplay(None, '%s', colour=(255, 0, 0), update=flight_data_recording),
]

def flightDataHandler(event, sender, data):
    global prev_flight_data
    text = str(data)
    if prev_flight_data != text:
        update_hud(hud, sender, data)
        prev_flight_data = text

def videoFrameHandler(event, sender, data):
    global video_player
    global video_recorder
    if video_player is None:
        cmd = [ 'mplayer', '-fps', '35', '-really-quiet' ]
        if wid is not None:
            cmd = cmd + [ '-wid', str(wid) ]
        video_player = Popen(cmd + ['-'], stdin=PIPE)

    try:
        video_player.stdin.write(data)
    except IOError as err:
        status_print(str(err))
        video_player = None

    try:
        if video_recorder:
            video_recorder.stdin.write(data)
    except IOError as err:
        status_print(str(err))
        video_recorder = None

def handleFileReceived(event, sender, data):
    global date_fmt
    # Create a file in ~/Pictures/ to receive image data from the drone.
    path = '%s/Pictures/tello-%s.jpeg' % (
        os.getenv('HOME'),
        datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S'))
    with open(path, 'wb') as fd:
        fd.write(data)
    status_print('Saved photo to %s' % path)

    
# class Drone():
#     def __init__(self):
#         self.drone = tellopy.Tello()
#         self.drone.connect()
#         self.drone.subscribe(self.drone.EVENT_FLIGHT_DATA, handler)
#         self.drone.subscribe(self.drone.EVENT_LOG_DATA, handler)
#         self.current_image = None
   
#     def set_speed(self, input):
#         self.speed
    
#     def counter_clockwise(self, speed):
#         self.drone.counter_clockwise(speed)
#     def clockwise(self, speed):
#         self.drone.clockwise(speed)
#     def forward(self, speed):
#         self.drone.forward(speed)
#     def backward(self, speed):
#         self.drone.backward(speed)
#     def left(self, speed):
#         self.drone.left(speed)
#     def right(self, speed):
#         self.drone.right(speed)
#     def up(self, speed):
#         self.drone.up(speed)
#     def down(self, speed):
#         self.drone.down(speed)
    

#     def throttle(self, speed):
#         self.drone.set_throttle(speed)
#     def yaw(self, speed):
#         self.drone.set_yaw(speed)
#     def pitch(self, speed):
#         self.drone.set_pitch(speed)
#     def roll(self, speed):
#         self.drone.set_roll(speed)
        


#     def takeoff(self):
#         time.sleep(.5)
#         self.drone.takeoff()
#     def land(self):
#         time.sleep(.5)
#         self.drone.land()
#     def sleep(self, sec):
#         print("before")
#         time.sleep(sec)
#         print("after")
#         self.drone.counter_clockwise(0)
#         self.drone.clockwise(0)
#         self.drone.forward(0)
#         self.drone.backward(0)
#         self.drone.left(0)
#         self.drone.right(0)
#         self.drone.up(0)
#         self.drone.down(0)
#     def video(self):
#         global buttons
#         global run_recv_thread
#         global new_image
        
#         d = threading.Thread(target=recv_thread, args=[self.drone])
#         d.daemon = True
#         d.start()
#         def show_img():
#             try:
#                 while 1:
#                     # loop with pygame.event.get() is too much tight w/o some sleep
#                     time.sleep(0.02)    
#                     if self.current_image is not new_image:
#                         cv2.imshow('Tello', new_image)
#                         self.current_image = new_image
#                         cv2.waitKey(1)
#             except KeyboardInterrupt as e:
#                 print(e)
#         t = threading.Thread(target=show_img)
#         t.daemon = True
#         t.start()