#!/usr/bin/env python3
#
# Copyright © 2010 Daniel Cordero
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""Routines for accessing the VNDB (visual novel database) API

Programs that use VNDB can use data from the site.
"""

import os
import time
import json
from socket import socket as ss
from getpass import getpass as gp
from configparser import ConfigParser as cp
import configparser

class VNDB():
	"""VNDB API implementation"""
	def connect(self):
		if self.status == "disconnected":
			self.sock = ss()
			self.sock.connect(self.endpoint)
			self.status = "connected"
	
	def login(self):
		"""Log in to the VNDB API"""
		if self.status == "logged-in":
			return
		if self.status == "disconnected":
			self.connect()

		self.chkconfig()

		request = '''
		{{
			"protocol": {:},
			"client": "{!s}",
			"clientver": {:},
			"username": "{!s}",
			"password": "{!s}"
		}}'''.format(
			self.protocol,
			self.client,
			self.clientver,
			self.username,
			self.password)
		data = VNDB.build("login",  request)
		data = self.sendrecv(data)
		if VNDB.parse(data) == "ok":
			self.status = "logged-in"
		else:
			print(VNDB.parse(data))

	def send(self, data):
		"""send data to socket"""
		if self.status == "connected" or self.status == "logged-in":
			if VNDB.parse(data) == "send":
				self.sock.sendall(data)
				self.lastsend = data
		else:
			self.login()
			self.send(data)
	
	def recv(self):
		"""get all data from socket."""
		data = self.sock.recv(1024)
		if not str(data, "utf-8").endswith("\x04"):
			data += self.recv()
		self.lastrecv = data
		return data
	
	def sendrecv(self, data):
		"""do a send and recv in one go"""
		self.send(data)
		return self.recv()
	
	def build(command, args):
		"""build a request"""
		fmt = "{} {}\x04".format(command, args)
		return bytes(fmt, "utf-8")

	def parse(data):
		"""parse a request or response string

		>>> VNDB.parse(b'ok\x04')
		'ok'
		>>> VNDB.parse(b'ok')
		'bad request'
		>>> VNDB.parse(b'''error {
		... 	"id": "parse",
		... 	"msg": "Invalid command or argument"
		... 	}\x04''')
		Parse error: Invalid command or argument.
		"""
		class Found(Exception): pass
		def hok(*ignore):
			"""Handler for the ok response"""
			return "ok"

		def herror(data):
			"""Handler for the error response"""
			# strip beg. "error " and EOT byte
			response = json.loads(data[6:-1])
			function = {
				"parse": VNDB.error.errparse,
				"missing": VNDB.error.errmissing,
				"badarg": VNDB.error.errbadarg,
				"needlogin": VNDB.error.errneedlogin,
				"throttled": VNDB.error.errthrottled,
				"auth": VNDB.error.errauth,
				"loggedin": VNDB.error.errloggedin,
				"sesslimit": VNDB.error.errsesslimit,
				"gettype": VNDB.error.errgettype,
				"getinfo": VNDB.error.errgetinfo,
				"filter": VNDB.error.errfilter
			}
			id = response.pop("id", None)
			return function.get(id, VNDB.error.errgeneric)(**response)

		def hlogin(data):
			"""Handler for the login command"""
			request = json.loads(data[6:-1])
			if request.keys() == set((
				"protocol",
				"client",
				"clientver",
				"username",
				"password")):
				return "send"

		def hget(data):
			"""Handler for parsing get commands"""
			def vn(flags, filters, options):
				def chkflags(flags):
					uflags = ["basic",
						  "detailed",
						  "anime",
						  "relations"]
					gflags = flags.split(",")
					for i in gflags:
						if i not in uflags:
							return "no-send"
					return "send"
				def chkfilters(filters):
					return "send"
				def chkoptions(options):
					return "send"

				if (chkflags(flags),
					chkfilters(filters),
					chkoptions(options)
				) == (	"send",
					"send",
					"send"):
					return "send"
				else:
					return "no-send"

			def release(flags, filters, options):
				return "send"
			def producer(flags, filters, options):
				return "send"

			data = data.split(" ", 3)
			data[3:] = data[3].rsplit(")", 1)
			types = {
				"vn": vn,
				"release": release,
				"producer": producer,
			}

			return types.get(data[1])(*data[2:])

		def hresults(data):
			"""handler for results responses"""
			return VNDB.hresults(data)

		try:
			data = str(data, "utf-8")
		except TypeError:
			pass

		if not data.endswith("\x04"):
			return "bad request"

		function = {
			"ok": hok,
			"error": herror,
			"login": hlogin,
			"get": hget,
			"results": hresults,
		}

		try:
			for command in function:
				if data.startswith(command):
					raise Found
		except Found:
			return function[command](data)

	def hresults(data):
		"""Handler for results response"""
		response = json.loads(data[8:-1])
		num = response['num']
		more = response['more']
		items = response['items']
		if num == 0:
			VNDB.error.errnoitems()
		return {"num":num, "more":more, "items":items}

	def logout(self, *ignore):
		"""close the socket"""
		self.sock.close()
		self.status = "disconnected"
	
	class error():
		"""Error handlers"""
		def errgeneric(**ignore):
			"""Unknown error message"""
			pass
		
		def errnoitems(**ignore):
			# This does not share the same
			# error namespace as the ones below.
			# See VNDB.hresults()
			print("No items returned.")

		def errparse(msg, **ignore):
			"""Return helpful message upon parsing error"""
			print("Parse error: {}.".format(msg))

		def errmissing(msg, field, **ignore):
			"""Return helpful message when missing a field"""
			pass

		def errbadarg(msg, field, **ignore):
			"""Return helpful message on bad arguments"""
			pass

		def errneedlogin(msg, **ignore):
			pass

		def errthrottled(msg, type, minwait, fullwait, **ignore):
			"""Handler for server throttles"""
			# TODO: find out how the messages are transmitted
			print("Throttled ({}): {}. Wait {}-{}s.".format(type, msg, minwait, fullwait))
			time.sleep(fullwait)
			

		def errauth(msg, **ignore):
			print("Auth: {}.".format(msg))

		def errloggedin(msg, **ignore):
			print("{}.".format(msg))

		def errsesslimit(msg, **ignore):
			pass

		def errgettype(msg, **ignore):
			pass

		def errgetinfo(msg, flag, **ignore):
			print("{}.".format(msg))

		def errfilter(msg, field, op, value, **ignore):
			pass
	
	def rcache(self, type, field, flags):
		# read cache
		"""Search the cache for a single field

		return the pythonic data if avaiilable
		otherwise return None when the program is forced to
		check the online database."""
		class Found(Exception): pass
		class NotFound(Exception): pass

		tf = os.path.join(self.home, type)
		if not os.path.isfile(tf):
			return None
		
		data = None
		with open(tf, "r") as ifh:
			try:
				for line in ifh:
					data = json.loads(line)
					if field['value'] == data[field['name']]:
						try:
							for i in flags.split(','):
								if data['flags'].find(i) == -1:
									raise NotFound
						except NotFound:
							return None
						if not data['time'] < time.time() - 60*60*24*28:
							raise Found
			except Found:
				return [data]
		return None

	def search(self, sstr, flags="basic", ftype="vn"):
		"""search the database

		sstr can be a v+, r+, p+; otherwise it's
		for the search filter"""
		class Found(Exception): pass
		type = {
			"v": "vn",
			"r": "release",
			"p": "producer",
		}

		request = None
		try:
			for i,j in type.items():
				if sstr.startswith(i) and sstr[1:].isdigit():
					ftype = j
					flags += ",details"
					raise Found
		except Found:
			id = int(sstr[1:])
			check = self.rcache(ftype, {"name":"id","value":id}, flags)
			if check == None:
				request = "{} {} (id = {})".format(j, flags, id)
			else:
				return {"num": 1, "more": False, "items": check}
		if request == None:
			request = '{} {} (search ~ "{}")'.format(ftype, flags, sstr)
		results = self.sendrecv(VNDB.build("get", request))
		parsed = VNDB.parse(results)
		if not parsed == None:
			for i in range(parsed['num']):
				parsed['items'][i].update({"flags": flags, "time": time.time()})
				self.scache(ftype, parsed['items'][i])
		return parsed

	def scache(self, type, data):
		"""save a dict into the cache"""
		class ToWrite(Exception): pass

		tf = os.path.join(self.home, type)
		if not os.path.isfile(tf):
			open(tf, "w").close()
		with open(tf, 'r') as ifh, open(tf+".tmp", 'w') as ofh:
			written = False
			for line in ifh:
				line = json.loads(line)
				try:
					if data['id'] == line['id']:
						for i in data['flags'].split(","):
							if line['flags'].find(i) == -1:
								raise ToWrite
						if line['time'] < time.time() - 60*60*24*28:
							raise ToWrite
				except ToWrite:	
					line = data
					written = True
				finally:
					ofh.write(json.dumps(line)+"\n")
			if written == False:
				ofh.write(json.dumps(data)+"\n")

		if os.name == "nt":
			os.remove(tf)
		os.rename(tf+".tmp", tf)

	def results(self, **out):
		def presults(key, value):
			print(key, ": ", sep="", end="")
			print(value)
		for i in range(out['num']):
			out['items'][i].pop("time")
			out['items'][i].pop("flags")
			for key, value in out['items'][i].items():
				if not key == "description":
					presults(key, value)
			try:
				value = out['items'][i].pop('description')
			except KeyError:
				pass
			else:
				if value:
					presults('description', value)
			if not i == out['num']:
				print()
	
	def chkconfig(self):
		home = self.home # XXX
		cname = os.path.join(home, 'config')
		if not os.path.isdir(home):
			os.mkdir(home)
		os.chdir(home)

		config = cp()
		config.read(cname)

		changed = False

		if not config.has_section("user"):
			config.add_section("user")
	
		try:
			username = config.get("user", "username")
		except configparser.NoOptionError:
			username = input("Username: ")
			changed = True
	
		try:
			password = config.get("user", "password")
		except configparser.NoOptionError:
			password = gp()
			changed = True
	
		if changed == True:
			config.set("user", "password", password)
			config.set("user", "username", username)
			mask = os.umask(0o077)
			config.write(open(cname, 'w'))
			os.umask(mask) # mask off global read
			print("Wrote configuration ({}).".format(cname))
			print("If you need to change your")
			print("details, please edit this file.")
			print()

		self.username = username
		self.password = password
		self.protocol = 1
		self.clientver = 0.1
		self.client = "pyvndb"

	def __init__(self):
		# Important variables

		self.home = os.path.join(os.getenv('HOME'), '.vnda')
		self.status = "disconnected"
		self.endpoint = ("api.vndb.org", 19534)

if __name__ == "__main__":
	vndb = VNDB()
	while True:
		try:
			line = input("Search: ")
			if line == "":
				continue
			res = vndb.search(line)
			if not res == None:
				vndb.results(**res)
			else:
				print("Cannot comply.")
		except (EOFError, KeyboardInterrupt):
			break
	if vndb.status == "connected" or vndb.status == "logged-in":
		vndb.logout()
	print()

