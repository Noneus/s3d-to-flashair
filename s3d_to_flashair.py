#!/usr/bin/python
#
# This file is part of s3d_to_flashair.  s3d_to_flashair is free software: you
# can redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright 2015 Jeff Rebeiro (jeff@rebeiro.net)

import hashlib
import itertools
import mimetools
import mimetypes
import optparse
import os
import platform
import shlex
import subprocess
import sys
import time
import urllib
import urllib2


DEFAULT_IP = '192.168.29.3'
GPX_CMD = '%s -p -m r1d %s'


class MultiPartForm(object):
    """Accumulate the data to be used when posting a form."""

    def __init__(self):
        self.form_fields = []
        self.files = []
        self.boundary = mimetools.choose_boundary()
        return
    
    def get_content_type(self):
        return 'multipart/form-data; boundary=%s' % self.boundary

    def add_field(self, name, value):
        """Add a simple field to the form data."""
        self.form_fields.append((name, value))
        return

    def add_file(self, fieldname, filename, fileHandle, mimetype=None):
        """Add a file to be uploaded."""
        body = fileHandle.read()
        if mimetype is None:
            mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        self.files.append((fieldname, filename, mimetype, body))
        return
    
    def __str__(self):
        """Return a string representing the form data, including attached files."""
        # Build a list of lists, each containing "lines" of the
        # request.  Each part is separated by a boundary string.
        # Once the list is built, return a string where each
        # line is separated by '\r\n'.  
        parts = []
        part_boundary = '--' + self.boundary
        
        # Add the form fields
        parts.extend(
            [ part_boundary,
              'Content-Disposition: form-data; name="%s"' % name,
              '',
              value,
            ]
            for name, value in self.form_fields
            )
        
        # Add the files to upload
        parts.extend(
            [ part_boundary,
              'Content-Disposition: file; name="%s"; filename="%s"' % \
                 (field_name, filename),
              'Content-Type: %s' % content_type,
              '',
              body,
            ]
            for field_name, filename, content_type, body in self.files
            )
        
        # Flatten the list and add closing boundary marker,
        # then return CR+LF separated data
        flattened = list(itertools.chain(*parts))
        flattened.append('--' + self.boundary + '--')
        flattened.append('')
        return '\r\n'.join(flattened)


def GenerateX3G(gcode_filepath, gpx_filepath):
  cmd = shlex.split(GPX_CMD % (gpx_filepath, gcode_filepath))
  print 'INFO: executing %s' % ' '.join(cmd)
  subprocess.call(cmd)


def GetLocalMD5(filename, blocksize=2**20):
  m = hashlib.md5()

  with open(filename, 'rb') as f:
    while True:
      buf = f.read(blocksize)

      if not buf:
        break

      m.update(buf)

  return m.hexdigest()


def GetRemoteMD5(url, max_file_size=100*1024*1024):
  remote = urllib2.urlopen(url)
  m = hashlib.md5()

  total_read = 0
  while True:
    data = remote.read(4096)
    total_read += 4096

    if not data or total_read > max_file_size:
      break
 
    m.update(data)
 
  return m.hexdigest()


def Speak(phrase):
  if sys.platform == 'darwin':
    subprocess.call(['say', phrase])


def GetDOSDateTime():
  """Returns a 32-bit int in DOS date/time format.
  
  From: http://blogs.msdn.com/b/oldnewthing/archive/2003/09/05/54806.aspx
  """
  t = time.localtime()
  return ((t.tm_year-1980)<<25) | (t.tm_mon << 21) | (t.tm_mday << 16) | (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec >>1)


if __name__ == '__main__':
    opt = optparse.OptionParser()
    opt.add_option('--delete', action="store_true", default=False)
    opt.add_option('--dir', '-d')
    opt.add_option('--file', '-f')
    opt.add_option('--ip', '-i', default=DEFAULT_IP)
    opt.add_option('--quiet', '-q', action="store_true", default=False)
    opt.add_option('--x3g', '-x', action="store_true", default=False)
 
    options, args = opt.parse_args()

    required_args = ['dir', 'file', 'ip']
    for required_arg in required_args:
      if not options.__dict__[required_arg]:
        err_msg = 'ERROR: %s must be specified' % required_arg
        print err_msg
        if not options.quiet:
          Speak(err_msg)
        parser.print_help()
        exit(-1)

    if platform.system == 'Windows':
      gpx_binary = 'gpx.exe'
    else:
      gpx_binary = 'gpx'
    
    gpx_filepath = os.path.join(options.dir, gpx_binary)
    if not options.quiet:
      Speak('generating x3g file')
    GenerateX3G(options.file, gpx_filepath)
    
    filename = os.path.basename(options.file)
    dirname = os.path.dirname(options.file)
    x3g_filename = os.path.splitext(filename)[0] + '.x3g'

    if not os.path.exists(os.path.join(dirname, x3g_filename)):
      time.sleep(10)
      if not os.path.exists(os.path.join(dirname, x3g_filename)):
        print 'ERROR: x3g file not found'
        if not options.quiet:
          Speak('ERROR, x3g file not found')
        sys.exit(1)

    if not options.quiet:
      Speak('uploading %s' % os.path.splitext(filename)[0])

    with open(os.path.join(dirname, x3g_filename)) as file_handle:
      form = MultiPartForm()
      form.add_file('file', x3g_filename, fileHandle=file_handle)
      
      urllib2.urlopen('http://%s/upload.cgi?FTIME=%s' % (options.ip, '0x%0.8X' % GetDOSDateTime()))

      request = urllib2.Request('http://%s/upload.cgi' % options.ip)
      request.add_header('User-agent', 'pyS3DFlashAir')
      body = str(form)
      request.add_header('Content-type', form.get_content_type())
      request.add_header('Content-length', len(body))
      request.add_data(body)

      urllib2.urlopen(request)

      if not options.quiet:
        Speak('verifying upload')
      remote_md5 = GetRemoteMD5('http://%s/%s' % (options.ip, x3g_filename))
      local_md5 = GetLocalMD5(os.path.join(dirname, x3g_filename))

      if remote_md5 != local_md5:
        print 'Upload failed!'
        if not options.quiet:
          Speak('Upload failed!')
      else:
        print 'Upload successful!'
        if not options.quiet:
          Speak('Upload successful!')

    if options.delete:
      os.remove(options.file)
      if options.x3g:
        os.remove(os.path.join(dirname, x3g_filename))

