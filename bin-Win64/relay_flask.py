from flask import Flask
import subprocess
import time,os,sys
import ctypes
from flask import request

app = Flask(__name__)

CHANNEL_SUCK = 2
CHANNEL_SPIN = 1

devids = []
hdev = None

# Fix the path below if the library is not in current dir.
libpath = "."
libfile = {'nt':   "usb_relay_device.dll", 
           'posix': "usb_relay_device.so",
           'darwin':"usb_relay_device.dylib",
           } [os.name]
if sys.version_info.major >= 3:
  def charpToString(charp):
     return str(ctypes.string_at(charp), 'ascii')
  def stringToCharp(s) :   
    return bytes(s, "ascii")
else:
  def charpToString(charp) :
     return str(ctypes.string_at(charp))
  def stringToCharp(s) :   
    return bytes(s)  #bytes(s, "ascii")

usb_relay_lib_funcs = [
  # TYpes: h=handle (pointer sized), p=pointer, i=int, e=error num (int), s=string
  ("usb_relay_device_enumerate",               'h', None),
  ("usb_relay_device_close",                   'e', 'h'),
  ("usb_relay_device_open_with_serial_number", 'h', 'si'),
  ("usb_relay_device_get_num_relays",          'i', 'h'),
  ("usb_relay_device_get_id_string",           's', 'h'),
  ("usb_relay_device_next_dev",                'h', 'h'),
  ("usb_relay_device_get_status_bitmap",       'i', 'h'),
  ("usb_relay_device_open_one_relay_channel",  'e', 'hi'),
  ("usb_relay_device_close_one_relay_channel", 'e', 'hi'),
  ("usb_relay_device_close_all_relay_channel", 'e', None)
  ]
  
def exc(msg):  return Exception(msg)

def fail(msg) : raise exc(msg)

def enumDevs():
  global devids
  devids = []
  enuminfo = L.usb_relay_device_enumerate()
  #print("enuminfo : ",enuminfo)
  while enuminfo :
    idstrp = L.usb_relay_device_get_id_string(enuminfo)
    print("idstrp : ",idstrp)
    idstr = charpToString(idstrp)
    print("idstr : ",idstr)
    assert len(idstr) == 5
    if not idstr in devids : devids.append(idstr)
    else : print("Warning! found duplicate ID=" + idstr)
    enuminfo = L.usb_relay_device_next_dev(enuminfo)

  print("Found devices: %d" % len(devids))
  
class L: pass   # Global object for the DLL
setattr(L, "dll", None)

# Load the C DLL ...
if not L.dll :
  print("Loading DLL: %s" % ('/'.join([libpath, libfile])))
try:
  L.dll = ctypes.CDLL( '/'.join([libpath, libfile]) )
except OSError:  
  fail("Failed load lib")
else:
  print("lib already open")


""" Get needed functions and configure types; call lib. init.
"""
assert L.dll

#Get lib version (my extension, not in the original dll)
libver = L.dll.usb_relay_device_lib_version()  
print("%s version: 0x%X" % (libfile,libver))

ret = L.dll.usb_relay_init()
if ret != 0 : fail("Failed lib init!")

"""
Tweak imported C functions
This is required in 64-bit mode. Optional for 32-bit (pointer size=int size)
Functions that return and receive ints or void work without specifying types.
"""
ctypemap = { 'e': ctypes.c_int, 'h':ctypes.c_void_p, 'p': ctypes.c_void_p,
		'i': ctypes.c_int, 's': ctypes.c_char_p}
for x in usb_relay_lib_funcs :
  fname, ret, param = x
  try:
    f = getattr(L.dll, fname)
  except Exception:  
    fail("Missing lib export:" + fname)

  ps = []
  if param :
    for p in param :
      ps.append( ctypemap[p] )
  f.restype = ctypemap[ret]
  f.argtypes = ps
  setattr(L, fname, f)

print("Searching for compatible devices")
enumDevs()
		
def openDevById(idstr):
  #Open by known ID:
  print("Opening " + idstr)
  h = L.usb_relay_device_open_with_serial_number(stringToCharp(idstr), 5)
  if not h: fail("Cannot open device with id="+idstr)
  global numch
  numch = L.usb_relay_device_get_num_relays(h)
  if numch <= 0 or numch > 8 : fail("Bad number of channels, can be 1-8")
  global hdev
  hdev = h  
  print("Number of relays on device with ID=%s: %d" % (idstr, numch))

@app.route('/open/<channel>')
def open(channel):
	subprocess.call('C:\\bin-Win64\\hidusb-relay-cmd.exe ON ' + channel)
	return 'Relay ' + channel + ' OPENED'

@app.route('/close/<channel>')
def close(channel):
	subprocess.call('C:\\bin-Win64\\hidusb-relay-cmd.exe OFF ' + channel)
	return 'Relay ' + channel + ' CLOSED'
	
@app.route('/suck_and_spin/<device_id>')
def suckandspin(device_id):
	try:
		print("request IP: ",request.remote_addr)
		if len(devids) != 0 and request.remote_addr == "15.1.24.3":
			# Test any 1st found dev .
			print("Testing relay with ID=" + devids[int(device_id)])
			openDevById(devids[int(device_id)])

			st = L.usb_relay_device_get_status_bitmap(hdev) 
			if st < 0:  fail("Bad status bitmask")
			print("Relay num ch=%d state=%x" % (numch, st))

			if(device_id == "0"):
				print("device_id : ", device_id)
				ret = L.usb_relay_device_open_one_relay_channel(hdev, CHANNEL_SUCK)
				print("open : ",ret)
				time.sleep(5)
				ret = L.usb_relay_device_close_one_relay_channel(hdev, CHANNEL_SUCK)
				print("close : ",ret)
				time.sleep(2)
				ret = L.usb_relay_device_open_one_relay_channel(hdev, CHANNEL_SPIN)
				print("open : ",ret)
				time.sleep(2)
				ret = L.usb_relay_device_close_one_relay_channel(hdev, CHANNEL_SPIN)
				print("close : ",ret)
				time.sleep(1)
			elif(device_id == "1"): 
				print("device_id : ", device_id)
				ret = L.usb_relay_device_open_one_relay_channel(hdev, 1)
				print("open : ",ret)
				time.sleep(10)
				ret = L.usb_relay_device_close_one_relay_channel(hdev, 1)
				print("close : ",ret)
				time.sleep(1)
			#closeDev()
		else:
			print("IP not allowed")
	finally:  
			#unloadLib()
			#open(CHANNEL_SUCK)
			#time.sleep(5)
			#close(CHANNEL_SUCK)
			#open(CHANNEL_SPIN)
			#close(CHANNEL_SPIN)
			return 'SUCK AND SPIN FINISHED'
