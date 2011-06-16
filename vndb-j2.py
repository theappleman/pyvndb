#!/usr/bin/python2

import os
import time
import simplejson as json
from socket import socket as ss

class vndb():
	"""VNDB API implementation"""
	def connect(self):
		if self.status == "disconnected":
			self.sock = ss()
			self.sock.connect(self.endpoint)
			self.status = "connected"
	
	def login(self):
		if self.status == "logged-in":
			return True
		if self.status == "disconnected":
			self.connect()

		request = '''{
			"protocol": %d,
			"client": "%s",
			"clientver": "%s"
		}''' % (1, "pyvndb-j", "2.1.0.1")

		data = self.build("login", request)
		data = self.send(data)
		data = self.recv()

		if self.parse(data):
			self.status = "logged-in"
			return True
		return False

	def logout(self):
		self.sock.close()
		self.status = "disconnected"

	def send(self, data):
		if self.parse(data) or self.login():
			self.sock.sendall(data)
			self.lastsend = data
		elif self.status == "disconnected":
			self.connect()
			self.send(data)
		# XXX: if everything fails?

	def recv(self):
		data = self.sock.recv(1024)
		if not data.endswith("\x04"):
			data += self.recv()
		self.lastrecv = data
		return data
	
	def sendrecv(self, data):
		self.send(data)
		return self.recv()
	
	def __init__(self):
		self.status = "disconnected"
		self.endpoint = ("api.vndb.org", 19534)
		self.home = os.path.join(os.getenv('HOME'), '.vnda')
	
	def build(self, command, args):
		fmt = "%s %s\x04" % (command, args)
		return fmt # .decode("utf-8")

	def csvset(self, string):
		return string.split(",")

	def save(self, table, data, flags):
		"""save /data/ (with flags /flags/) to /table/."""

		class ToWrite(Exception): pass

		data['time'] = time.time()
		data['flags'] = flags

		tf = os.path.join(self.home, table)
		if not os.path.isfile(tf): # File non-existant
			open(tf, "w").close()
		with open(tf, "r") as ifh:
			with open(tf + ".tmp", "w") as ofh:
				written = False
				for line in ifh:
					line = json.loads(line)
					try:
						if data['id'] == line['id']: # Find a matching ID
							for i in self.csvset(data['flags']):
								if line['flags'].find(i) == -1: # Find for flags not already in the table already
									raise ToWrite
							if line['time'] < time.time() - 60*60*24*28: # If the data is older than 1 month regardless
								raise ToWrite
					except ToWrite:
						line = data
					finally:
						ofh.write(json.dumps(line) + "\n")
				if written == False:
					ofh.write(json.dumps(data) + "\n")

		if os.name == "nt":
			os.remove(tf)
		os.rename(tf + ".tmp", tf)


	def get(self, table, field, flags):
		"""Search the database for exact matches against a single
		database field

		Only valid entries (ones that contain all the required info
		and are less than 28 days old) are returned.
		
		return (0, {}) if nothing was found.
		
		(number of entries, [entries])"""

		class Found(Exception): pass
		class NotFound(Exception): pass

		tf = os.path.join(self.home, table)
		if not os.path.isfile(tf):
			return (0, {})

		data = None

		with open(tf, "r") as ifh:
			try:
				for line in ifh:
					data = json.loads(line)
					if field['value'] == data[field['name']]:
						try:
							for i in self.csvset(flags):
								if data['flags'].find(i) == -1:
									raise NotFound
						except NotFound:
							return (0, {})
						if not data['time'] < time.time() - 60*60*24*28:
							raise Found
			except Found:
				return (1, data) #XXX: CHECKME

		return (0, {})

	def parse(self, data):
		"""Turn raw bytes into usable actions

		`data` is the response in the form of:
			login:
				ok
				error {}
			get:
				results {}
				error {}
		
		"""

		def hok(msg, *ignore):
			return True

		def hres(msg):
			return True, json.loads(msg[8:-1])

		def herr(msg):
			data = json.loads(msg[6:-1])
			for key, value in data.items():
				print key + ":", value
			return False, data

		def hlogin(msg):
			return True

		class Found(Exception): pass

		#data = data.encode("utf-8")

		if not data.endswith("\x04"):
			return "bad request"

		hanfun = {
			"ok": hok,
			"error": herr,
			"login": hlogin,
			"results": hres,
		}

		try:
			for command in hanfun:
				if data.startswith(command):
					raise Found
		except Found:
			return hanfun[command](data)

	def search(self, sstr, flags="basic", stype="vn"):
		mtype = {
			"v": "vn",
			"r": "release",
			"p": "producer",
		}

		class Found(Exception): pass

		request = None
		try:
			for i,j in mtype.items():
				if sstr.startswith(i) and sstr[1:].isdigit():
					stype = j
					if not "details" in vn.csvset(flags):
						flags += ",details"
					raise Found
		except Found:
			iid = int(sstr[1:])
			(check, res) = self.get(mtype[sstr[0]],
				{"name": "id", "value": iid},
				flags)

			if check == 1:
				return {"num": 1, "more": False, "items": [res]}
			else:
				request = '%s %s (id = %s)' % (stype, flags, iid)

		if request == None:
			request = '%s %s (search ~ "%s")' % (stype, flags, sstr)

		results = self.sendrecv(self.build("get", request))

		(check, res) = self.parse(results)

		# We cache the data for use with v/p/r+
		if check:
			for item in res.get("items"):
				self.save(stype, item, flags)
			return res
		return {"num": 0, "more": False, "items": []}
	
	def results(self, out):
		def presults(key, value, tab=""):
			if value == None:
				return False
			print tab + key + ": ",
			if type(value) is list:
				print ", ".join([i.encode() for i in value])
			elif type(value) is dict:
				nl = False
				for k,v in value.items():
					if presults(k, v, tab + "\t"):
						nl = True
					else:
						nl = nl == True
				if not nl:
					print
			else:
				print value
			return True

		for i in range(out['num']):
			item = out['items'][i]
			presults('id', item['id']) #XXX: need to find type
			for j in ["title", "name", "original", "released", #vr, p, vr, vr
				"type", "patch", "freeware", "doujin", #rp, r
				"languages", "orig_lang", "language", #vr, v, p
				"website", "notes", "minage", "gtin", #r
				"catalog",  "platforms", "media", #r, vr, r
				"aliases", "length", "description", #vp, v, vp
				"vn", "producers", #r
				"links", "image", "anime",
				"relations"]: #vp
				if item.has_key(j) and not item.get(j) == None:
					presults(j, item[j])

			if not i == out['num']:
				print


if __name__ == "__main__":
	vn = vndb()

	# Here are a couple of example applications for the class
	while True:
		try:
			line = raw_input("Search: ")
			if line == "":
				continue
			res = vn.search(line)
			if not res['num'] == 0:
				vn.results(res)
			else:
				print "Cannot comply."
		except (EOFError, KeyboardInterrupt):
			break
	if vn.status == "connected" or vn.status == "logged-in":
		vn.logout()
	print

#	vn.results(vn.search("v5"))
#	vn.results(vn.search("museum"))
#	vn.results(vn.search("fluffy", stype="producer", flags="details"))
