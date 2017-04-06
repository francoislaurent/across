
from __future__ import print_function

import time
import calendar
import os
import sys
import itertools
from syncacre.encryption import Plain
from math import *


class Manager(object):

	def __init__(self, relay, path=None, address=None, directory=None, mode=None, \
		encryption=Plain(None), timestamp=True, refresh=None, verbose=True, clientname=None, \
		**relay_args):
		if path[-1] != '/':
			path += '/'
		self.path = path
		self.dir = directory
		self.mode = mode
		self.encryption = encryption
		if timestamp is True:
			timestamp = '%y%m%d_%H%M%S'
		self.timestamp = timestamp
		self.refresh = refresh
		self.verbose = verbose
		self.pop_args = {}
		if clientname:
			self.pop_args['client_name'] = clientname
		self.relay = relay(address, **relay_args)

	def run(self):
		self.logBegin('connecting with {}', self.relay.address)
		ok = self.relay.open()
		self.logEnd(ok)
		try:
			while True:
				if self.mode is None or self.mode == 'download':
					self.download()
				if self.mode is None or self.mode == 'upload':
					self.upload()
				if self.refresh:
					self.logBegin('sleeping {} seconds', self.refresh)
					time.sleep(self.refresh)
					self.logEnd()
				else:
					break
		except KeyboardInterrupt:
			pass
		self.relay.close()

	def download(self):
		remote = self.relay.listReady(self.dir)
		#print(('Manager.download: remote', remote))
		for filename in remote:
			local_file = os.path.join(self.path, filename)
			remote_file = os.path.join(self.dir, filename)
			last_modified = None
			if self.timestamp:
				placeholder = self.relay.getPlaceholder(remote_file)
				if placeholder:
					with open(placeholder, 'r') as f:
						last_modified = f.readline().rstrip()
					os.unlink(placeholder)
					last_modified = time.strptime(last_modified, self.timestamp)
					last_modified = calendar.timegm(last_modified) # remote_mtime
			if os.path.isfile(local_file):
				if last_modified and last_modified <= floor(os.path.getmtime(local_file)):
					# local_mtime = os.path.getmtime(local_file)
					continue
				msg = 'updating local file {}'
			else:
				msg = 'downloading file {}'
			temp_file = self.encryption.prepare(local_file)
			self.logBegin(msg, filename)
			ok = self.relay.pop(remote_file, temp_file, blocking=False, **self.pop_args)
			self.logEnd(ok)
			self.encryption.decrypt(temp_file, local_file)
			if last_modified:
				os.utime(local_file, (time.time(), last_modified))

	def upload(self):
		local = self.localFiles()
		remote = self.relay.listTransfered(self.dir, end2end=False)
		#print(('Manager.upload: local, remote', local, remote))
		for local_file in local:
			filename = local_file[len(self.path):] # relative path
			modified = False # if no remote copy, this is ignored
			if self.timestamp: # check file last modification time
				local_mtime = floor(os.path.getmtime(local_file))
				last_modified = time.gmtime(local_mtime) # UTC
				last_modified = time.strftime(self.timestamp, last_modified)
				if filename in remote:
					remote_file = os.path.join(self.dir, filename)
					placeholder = self.relay.getPlaceholder(remote_file)
					if placeholder:
						with open(placeholder, 'r') as f:
							remote_mtime = f.readline().rstrip()
						os.unlink(placeholder)
						remote_mtime = time.strptime(remote_mtime, self.timestamp)
						remote_mtime = calendar.timegm(remote_mtime)
						modified = remote_mtime < local_mtime
					#else: (TODO) directly read mtime on remote copy?
			else:
				last_modified = None
			if filename not in remote or modified:
				# TODO: check disk usage on relay
				temp_file = self.encryption.encrypt(local_file)
				self.logBegin('uploading file {}', filename)
				ok = self.relay.push(temp_file, self.dir, \
					relative_path=filename, blocking=False, \
					last_modified=last_modified)
				self.logEnd(ok)
				self.encryption.finalize(temp_file) # delete encrypted copy

	def logBegin(self, msg, *args):
		if self.verbose:
			print((msg + '... ').format(*args), end='')
			sys.stdout.flush()

	def logEnd(self, ok=True):
		if self.verbose:
			if ok is None:
				print('')
			elif ok:
				print('[done]')
			else:
				print('[failed]')

	def localFiles(self, path=None):
		if path is None:
			path = self.path
		ls = [ os.path.join(path, file) for file in os.listdir(path) if file[0] != '.' ]
		local = itertools.chain([ file for file in ls if os.path.isfile(file) ], \
			*[ self.localFiles(file) for file in ls if os.path.isdir(file) ])
		return list(local)


