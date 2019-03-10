#!/usr/bin/env python
# Copyright 2011 Valery Yundin
#
# This file is free software
# project page https://github.com/Vayu/skypelog
#

"""
Read 'Skype for Linux' *.dbb files


Read and parse Skype database files + simple export of chat message history.
See README for details
"""

from __future__ import with_statement
import struct
import time
import json
import base64
import os
import platform


__all__ = ['SkypeDBB', 'SkypeMsgDBB', 'SkypeMsg',
           'SkypeAccDBB', 'SkypeAcc','SkypeContactDBB', 'SkypeContact',
           'SkypeChatDBB', 'SkypeChat', 'SkypeChatMemberDBB', 'SkypeChatMember',
           'SkypeCall', 'SkypeCallDBB']


class SkypeDBB:
    """Read and parse DBB files, return dictionary records"""

    def guessmaxsize(self, filename):
        """Guess maximum record size from the file name """
        k = len(filename) - 1
        while not filename[k].isdigit():
            k -= 1
        i = k
        while filename[i].isdigit():
            i -= 1
        maxsize = int(filename[i + 1:k + 1])
        return maxsize

    def read7bitnum(self, rec, pos):
        """Parse 7-bit encoded number at 'pos' in 'rec'"""
        code = 0
        shift = 0
        while True:
            char = ord(rec[pos])
            code = code + ((char & 0x7F) << shift)
            shift += 7
            pos += 1
            if char & 0x80 == 0:
                break
        return (code, pos)

    def readrecord(self, num):
        """Return num'th record in file"""
        if num >= self.rnum:
            raise IndexError("Record number %d not found" % num)
        self.f.seek(self.stride * num, os.SEEK_SET)
        return self.parserecord(self.f.read(self.stride))

    def parserecord(self, rec):
        """Parse record in string 'rec'"""
        if rec[:4] != 'l33l':
            raise RuntimeError("Invalid header magic %s" % repr(rec[:4]))
        res = {}
        recsize, recid = struct.unpack("<II", rec[4:12])
        res[-1] = recid
        pos = 17
        while pos < recsize + 8:
            ftype = rec[pos]
            pos += 1
            if ftype == '\x00':
                code, pos = self.read7bitnum(rec, pos)
                val, pos = self.read7bitnum(rec, pos)
            elif ftype == '\x03':
                code, pos = self.read7bitnum(rec, pos)
                eos = rec.find('\x00', pos)
                assert (eos != -1)
                val = rec[pos:eos]
                pos = eos + 1
            elif ftype == '\x04':
                code, pos = self.read7bitnum(rec, pos)
                bsize, pos = self.read7bitnum(rec, pos)
                val = base64.b64encode(rec[pos:pos + bsize])
                pos = pos + bsize
            else:
                raise RuntimeError("Unknown field type %s at offset %d" %
                                   (hex(ord(ftype)), pos))
            res[code] = val
        return res

    def records(self):
        """Iterate over all records in file"""
        self.f.seek(0, os.SEEK_SET)
        for rec in iter(lambda: self.f.read(self.stride), ''):
            yield self.parserecord(rec)
        raise StopIteration

    def __init__(self, filename, maxsize=0):
        """Open .dbb file with record size 'maxsize' (optional)"""
        if maxsize == 0:
            maxsize = self.guessmaxsize(filename)
        self.stride = 8 + maxsize
        self.f = open(filename, 'rb')
        self.f.seek(0, os.SEEK_END)
        self.flen = self.f.tell()
        self.f.seek(0, os.SEEK_SET)
        self.rnum = int((self.flen - 1) / self.stride + 1)

    def __del__(self):
        self.f.close()


class SkypeObject:
    """Baseclass for DBB records"""

    __slots__ = ()

    def __init__(self, data):
        for key, val in data.iteritems():
            if key in self.FIELD_NAMES:
                setattr(self, self.FIELD_NAMES[key], val)
            else:
                print ("%s: unknown field %d = %s"
                        % (self.__class__.__name__, key, repr(val)))

    def __str__(self):
        return self.__dict__.__str__()


class SkypeMsgDBB(SkypeDBB):
    """Read and parse Message DBB files chatmsgDDDDD.dbb"""

    def parserecord(self, rec):
        """Wrap parserecord return in SkypeMsg class"""
        return SkypeMsg(SkypeDBB.parserecord(self, rec))


class SkypeMsg(SkypeObject):
    """Represent and format chat message records"""

    FIELD_NAMES = {   -1 : 'recid',
                      -2 : 'ctime',
                       3 : 'pk_id',
                       7 : 'crc',
                      11 : 'remote_id',
                     480 : 'chatname',
                     485 : 'timestamp',
                     488 : 'author',
                     492 : 'from_dispname',
                     497 : 'chatmsg_type',  # 1 - addmembers, 2 - createchatwith,
                                            # 3 - said, 4- left, 5 - changetopic
                     500 : 'users_added',
                     505 : 'leavereason',   # 6 - unsubdcribe
                     508 : 'body_xml',
                     513 : 'chatmsg_status',  # 1 - sending, 2 - sent,
                                              # 3 - recieved, 4 - read
                     517 : 'body_is_rawxml',
                     888 : 'edited_by',
                     893 : 'edited_timestamp',
                    3160 : 'dialog_partner',
                    3170 : 'guid',             # binary
                    3845 : 'int3845',
                    3857 : 'int3857',
                    3877 : 'int3877',
                   }

    __slots__ = FIELD_NAMES.values()

    def __init__(self, data):
        if 485 in data:
            data[-2] = time.ctime(data[485])
        else:
            data[-2] = 'Unknown'
        SkypeObject.__init__(self, data)
        if 'dialog_partner' not in self.__dict__:
            try:
                setattr(self, 'dialog_partner', 'chat_%s' % self.chatname.split(';')[1])
            except:
                setattr(self, 'dialog_partner', 'None')

    def json_full(self):
        return json.dumps(self.__dict__, sort_keys=True, ensure_ascii=False)

    def json_compact(self):
        """Output in JSON only fields displayed in client UI"""
        if 'body_xml' not in self.__dict__:  # not 'said' msg
            return ""
        s = '''\
{\
"dialog_partner":"%(dialog_partner)s",\
"timestamp":%(timestamp)d,\
"ctime":"%(ctime)s",\
"from_dispname":"%(from_dispname)s",\
"body_xml":\
''' % self.__dict__
        s += json.dumps(self.body_xml, ensure_ascii=False) + '}'
        return s

    def html_compact(self):
        """Output in HTML only fields displayed in client UI"""
        if 'body_xml' not in self.__dict__:  # not 'said' msg
            return ""
        s = '''\
<div class=msg>\
<!-- %(dialog_partner)s %(timestamp)d %(pk_id)d -->\
<span class=time>%(ctime)s</span>\
''' % self.__dict__
        if self.dialog_partner == self.author:
            s += "<span class=from>%(from_dispname)s</span>" % self.__dict__
        else:
            s += "<span class=me>%(from_dispname)s</span>" % self.__dict__
        msgbody = self.body_xml
        msgbody = msgbody.replace('&', '&amp;')
        msgbody = msgbody.replace('<', '&lt;')
        msgbody = msgbody.replace('>', '&gt;')
        msgbody = msgbody.replace('\n', '<br>\n')
        s += msgbody + "</div>"
        return s


class SkypeAccDBB(SkypeDBB):
    """Read and parse account DBB files profileDDDDD.dbb"""

    def parserecord(self, rec):
        """Wrap parserecord return in SkypeMsg class"""
        return SkypeAcc(SkypeDBB.parserecord(self, rec))


class SkypeAcc(SkypeObject):
    """Represent and format account records"""

    FIELD_NAMES = {   -1 : 'recid',
                       7 : 'emailbin',             # binary
                      11 : 'int11',
                      16 : 'skypename',
                      20 : 'fullname',
                      29 : 'birthday',
                      33 : 'gender',
                      36 : 'languages',
                      40 : 'country',
                      44 : 'province',
                      48 : 'city',
                      52 : 'phone_home',
                      56 : 'phone_office',
                      60 : 'phone_mobile',
                      64 : 'emails',
                      68 : 'homepage',
                      72 : 'about',
                      77 : 'profile_timestamp',
                      91 : 'profile_attachments',  # binary
                     104 : 'mood_text',
                     109 : 'timezone',
                     116 : 'ipcountry',
                     150 : 'avatar_image',         # binary
                     296 : 'balance_currency',
                     301 : 'balance',
                     641 : 'int641',
                     645 : 'int645',
                     657 : 'int657',
                     820 : 'rich_mood_text',
                    3205 : 'registration_timestamp',
                    3217 : 'int3217',
                   }

    __slots__ = FIELD_NAMES.values()


class SkypeContactDBB(SkypeDBB):
    """Read and parse contacts DBB files userDDDDD.dbb"""

    def parserecord(self, rec):
        """Wrap parserecord return in SkypeMsg class"""
        return SkypeContact(SkypeDBB.parserecord(self, rec))


class SkypeContact(SkypeObject):
    """Represent and format contacts records"""

    FIELD_NAMES = {   -1 : 'recid',
                       3 : 'authorization_certificate',  # binary
                      11 : 'certificate_send_count',
                      15 : 'account_modification_serial_nr',
                      19 : 'saved_directory_blob',       # binary
                      16 : 'skypename',
                      20 : 'fullname',
                      24 : 'phone',
                      27 : 'server_synced',
                      29 : 'birthday',
                      33 : 'gender',
                      35 : 'last_used_networktime',
                      36 : 'languages',
                      40 : 'country',
                      44 : 'province',
                      48 : 'city',
                      52 : 'phone_home',
                      56 : 'phone_office',
                      59 : 'blob59',                 # binary
                      60 : 'phone_mobile',
                      64 : 'emails',
                      68 : 'homepage',
                      72 : 'about',
                      77 : 'time77',
                      93 : 'given_authlevel',
                      99 : 'int99',
                     109 : 'int109',
                     113 : 'nrof_authed_buddies',
                     115 : 'int115',
                     119 : 'blob119',
                     121 : 'buddystatus',
                     125 : 'isauthorized',
                     129 : 'isblocked',
                     132 : 'given_displayname',
                     141 : 'time141',
                     146 : 'blob146',                # binary
                     150 : 'avatar_image',           # binary
                     157 : 'lastcalled_time',
                     165 : 'system_account',         # eg echo123
                    1006 : 'int1006',
                    1007 : 'int1007',
                    1008 : 'int1008',
                    1009 : 'int1009',
                    1010 : 'int1010',
                    1011 : 'str1011',
                    1019 : 'extprop_seen_birthday',  # binary
                    1022 : 'time1022',
                   }

    __slots__ = FIELD_NAMES.values()


class SkypeChatDBB(SkypeDBB):
    """Read and parse account DBB files chatDDDDD.dbb"""

    def parserecord(self, rec):
        """Wrap parserecord return in SkypeMsg class"""
        return SkypeChat(SkypeDBB.parserecord(self, rec))


class SkypeChat(SkypeObject):
    """Represent and format chat records"""

    FIELD_NAMES = {   -1 : 'recid',
                       3 : 'int3',
                      15 : 'blob15',  # binary
                      19 : 'one19',
                      23 : 'time23',
                      31 : 'zero13',
                      39 : 'blob',    # binary
                      47 : 'one47',
                      51 : 'cachedat',
                      55 : 'topicauto',
                      59 : 'one59',
                     440 : 'chatname',
                     445 : 'timestamp',
                     448 : 'user448',
                     453 : 'type',
                     456 : 'posters',
                     460 : 'members',
                     464 : 'topic',
                     468 : 'activemembers',
                     472 : 'friendly_name',
                     561 : 'bookmarked',
                     565 : 'activity_time',
                     569 : 'mystatus',
                     581 : 'moodchat',
                     638 : 'chatpicture',  # binary
                     828 : 'user828',
                    1006 : 'int1006',  # this and 3 below, related to multichat
                    1007 : 'int1007',
                    1010 : 'int1010',
                    1020 : 'int1020',
                    3081 : 'four3081',
                    3096 : 'topic_xml',
                   }

    __slots__ = FIELD_NAMES.values()


class SkypeChatMemberDBB(SkypeDBB):
    """Read and parse account DBB files chatmemberDDDDD.dbb"""

    def parserecord(self, rec):
        """Wrap parserecord return in SkypeMsg class"""
        return SkypeChatMember(SkypeDBB.parserecord(self, rec))


class SkypeChatMember(SkypeObject):
    """Represent and format chatmember records"""

    FIELD_NAMES = {   -1 : 'recid',
                     584 : 'chatname',
                     593 : 'role',
                     588 : 'identity',
                     597 : 'isactive',
                   }

    __slots__ = FIELD_NAMES.values()

class SkypeCallDBB(SkypeDBB):
    def parserecord(self, rec):
        return SkypeCall(SkypeDBB.parserecord(self, rec))

    def json_full(self):
        return json.dumps(self.__dict__, sort_keys=True, ensure_ascii=False)

class SkypeCall(SkypeObject):
    """Represent and format call records"""

    # calls contain separate records with different keys for the host and each member
    # these can grouped by the call name, and member records also contain a reference
    # to the host's record ID.
    # key names mostly taken from main.db equivalent
    FIELD_NAMES = {   -1 : 'recid',
                      -2 : 'ctime',
                      -3 : 'is_host',
                      -4 : 'gname',
                       3 : 'str3',
                       7 : 'call_recid',
                      11 : 'str11',
                     161 : 'begin_timestamp',
                     252 : 'topic',
                     184 : 'call_name',
                     # nonzero only when joining after the call started
                     693 : 'start_timestamp',

                     # booleans inferred from corresponding main.db positions
                     813 : 'is_muted',
                     817 : 'is_unseen_missed',

                     840 : 'host_identity',
                     849 : 'duration',
                     868 : 'name',
                     917 : 'int917',

                     # member-specific keys
                     920 : 'identity',
                     924 : 'dispname',
                     933 : 'call_duration',
                     945 : 'type',
                     949 : 'status',
                     953 : 'failurereason',
                     964 : 'pstn_statustext',
                     3296: 'real_identity',
                     3301: 'member_start_timestamp',
                   }

    __slots__ = FIELD_NAMES.values()

    def __init__(self, data):
        SkypeObject.__init__(self, data)
        # add the call name to "gname" irrespective of whether this is a host record
        self.is_host = 'name' in self.__dict__
        if self.is_host:
            self.gname = self.name
            try:
                self.ctime = time.ctime(self.begin_timestamp)
            except:
                self.ctime = 'Unknown'
        else:
            if 'call_name' in self.__dict__:
                self.gname = self.call_name
            try:
                self.ctime = time.ctime(self.member_start_timestamp)
            except:
                self.ctime = 'Unknown'

    def json_full(self):
        return json.dumps(self.__dict__, sort_keys=True, ensure_ascii=False)

# -----------------------------------------------------------------------------
# End of API, local functions follow
# -----------------------------------------------------------------------------


def forskypedbbs(func, prefix):
    """Call 'func' on every 'prefix'xxx.dbb"""
    userdirs = []
    if platform.system() == "Darwin":
      skype = os.path.join(os.environ["HOME"], "Library/Application Support/Skype")
    else:
      skype = os.path.join(os.environ["HOME"], ".Skype")
    for name in os.listdir(skype):
        pathname = os.path.join(skype, name)
        if os.path.isdir(pathname):
            userdirs.append( (name, pathname) )
    for user, home in userdirs:
        chatdbbs = []
        for name in os.listdir(home):
            if name.startswith(prefix) and name.endswith(".dbb"):
                chatdbbs.append(os.path.join(home, name))
        if chatdbbs:
            func(user, chatdbbs)


def dumpmsg_json_full_helper(user, chatdbbs):
    """Dump full messages from 'chatdbbs' files to 'user'.js file (unsorted)"""
    fname = user + '.js'
    print "writing %s ..." % fname
    with open(fname, 'wb') as f:
        for filename in chatdbbs:
            msgdbb = SkypeMsgDBB(filename)
            for r in msgdbb.records():
                f.write(r.json_full() + ",\n")

def dumpcall_json_full_helper(user, chatdbbs):
    """Dump full messages from 'chatdbbs' files to 'user'.js file (unsorted)"""
    fname = user + '.calls.js'
    print "writing %s ..." % fname
    with open(fname, 'wb') as f:
        for filename in chatdbbs:
            msgdbb = SkypeCallDBB(filename)
            for r in msgdbb.records():
                f.write(r.json_full() + ",\n")

def dumpmsg_json_full():
    """Dump full chat logs for every user"""
    forskypedbbs(dumpmsg_json_full_helper, "chatmsg")

def dumpcall_json_full():
    """Dump full chat logs for every user"""
    forskypedbbs(dumpcall_json_full_helper, "call")

def dumpmsg_json_compact_helper(user, chatdbbs):
    """Dump messages from 'chatdbbs' files to 'user'.js file (unsorted)"""
    fname = user + '.js'
    print "writing %s ..." % fname
    with open(fname, 'wb') as f:
        for filename in chatdbbs:
            msgdbb = SkypeMsgDBB(filename)
            for r in msgdbb.records():
                f.write(r.json_compact() + ",\n")


def dumpmsg_json_compact():
    """Dump chat logs for every user"""
    forskypedbbs(dumpmsg_json_compact_helper, "chatmsg")


def dumpmsg_html_helper(user, chatdbbs):
    """Dump messages from 'chatdbbs' files to 'user'-user.html file (sorted)"""
    HEAD = '''\
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html><head><meta http-equiv="content-type" content="text/html; charset=UTF-8">
<title>[TITLE]</title><style>
div.msg span.time:before { content: "["; }
div.msg span.time:after { content: "]"; }
div.msg span.time { color: #7F7F7F; margin: 0ex 0.2ex 0ex 0.2ex; }
div.msg span.me:after { content: ": "; }
div.msg span.me { font-weight: bold; color: #0063CC; margin: 0ex 0.5ex 0ex 0.5ex; }
div.msg span.from:after { content: ": "; }
div.msg span.from { font-weight: bold; color: #098DDE; margin: 0ex 0.5ex 0ex 0.5ex; }
</style></head><body>
'''
    contacts = {}
    for filename in chatdbbs:
        msgdbb = SkypeMsgDBB(filename)
        for r in msgdbb.records():
            if r.dialog_partner not in contacts:
                contacts[r.dialog_partner] = []
            msg = r.html_compact()
            if msg:
                contacts[r.dialog_partner].append(msg)

    for name in contacts.keys():
        messages = sorted(contacts[name])
        contacts[name] = None
        if len(messages) == 0:
            continue

        seqn = 0
        tail = "</body></html>"
        global MODE
        fmode = MODE
        fname = "%s-%s-%d.html" % (user, name, seqn)
        if os.path.exists(fname):
            if fmode == 'guess':
                with open(fname, 'rb') as f:
                    for line in f:
                        if line.startswith('<div class=msg>'):
                            if not line.startswith(messages[0]):
                                fmode = 'append'
                            else:
                                fmode = 'overwrite'
                            break
        else:
            fmode = 'overwrite'

        if fmode == 'append':
            while os.path.exists(fname):
                seqn += 1
                fname = "%s-%s-%d.html" % (user, name, seqn)
            seqn -= 1
            fname = "%s-%s-%d.html" % (user, name, seqn)
            f = open(fname, 'r+b')
            f.seek(-len(tail), 2)
            if f.readline() != tail:
                f.seek(-len(tail), 2)
                print repr(f.readline()), repr(tail)
                f.close()
                fmode = 'overwrite'
                print "Bad end of file: %s" % fname
                seqn += 1
                fname = "%s-%s-%d.html" % (user, name, seqn)
            else:
                f.seek(-len(tail), 2)

        if fmode != 'append':  # not else !!!
            f = open(fname, 'wb')

        idx = 0
        bytes = f.tell()
        print fname, fmode

        while True:
            with f:
                if fmode != 'append':
                    head = HEAD.replace("[TITLE]", "'%s' chats with '%s' part %d"
                                        % (user, name, seqn))
                    f.write(head)
                    bytes += len(head)
                while bytes < SIZE_LIMIT and idx < len(messages):
                    f.write(messages[idx])
                    f.write("\n")
                    bytes += len(messages[idx]) + 1
                    idx += 1
                f.write(tail)
            if idx < len(messages):
                bytes = 0
                seqn += 1
                fname = "%s-%s-%d.html" % (user, name, seqn)
                f = open(fname, 'wb')
            else:
                break


def dumpmsg_html():
    """Dump chat logs for every user"""
    forskypedbbs(dumpmsg_html_helper, "chatmsg")


def usage():
    print """\
Usage: skypelog [OPTION]...
Dump Skype chat history to files in the current directory

Option:
  -h, --help                Show this help message
  -j, --json={compact,full,calls} Save history for each user in *.js file (unsorted)
  -t, --html                Save history for user/contact pair in *.html files
  -m, --mode={append,overwrite} HTML output mode (guess by default)
  -l, --limit=bytes[KM]     Limit output html file size
"""
    sys.exit()


def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hj:tm:l:",
                                   ["help", "json=", "html", "mode=", "limit="])
    except getopt.GetoptError, err:
        print str(err)
        usage()
        sys.exit(2)
    if not opts:
        opts = [("-h", "")]

    global SIZE_LIMIT
    global MODE
    action = []
    SIZE_LIMIT = 1024**3
    MODE = "guess"
    for op, arg in opts:
        if op in ("-h", "--help"):
            usage()
        elif op in ("-j", "--json"):
            if arg in ("compact"):
                print "Dumping chat history to JSON (compact)..."
                action.append('dumpmsg_json_compact')
            elif arg in ("full"):
                print "Dumping chat history to JSON (full)..."
                action.append('dumpmsg_json_full')
            elif arg in ("calls"):
                print "Dumping call history to JSON (full)..."
                action.append('dumpcall_json_full')
            else:
                print "JSON: unknown argument '%s'" % arg
                action.append('usage')
        elif op in ("-t", "--html"):
            print "Dumping chat history to HTML..."
            action.append('dumpmsg_html')
        elif op in ("-m", "--mode"):
            if arg in ["append", "overwrite", "guess"]:
                MODE = arg
                print "Setting mode to '%s'" % MODE
            else:
                print "MODE: bad argument '%s'" % arg
                action.append('usage')
        elif op in ("-l", "--limit"):
            factors = {'K' : 1024, 'M' : 1024**2}
            unit = 1
            val = arg
            if len(arg)>1 and arg[-1] in factors:
                unit = factors[arg[-1]]
                val = arg[:-1]
            try:
                SIZE_LIMIT = int(val)*unit
                if SIZE_LIMIT < 1024:
                    raise ValueError()
                print "Setting html file size limit to %d" % SIZE_LIMIT
            except ValueError:
                print "LIMIT: bad argument '%s'" % arg
                action.append('usage')
        else:
            assert False, "unhandled option"

    if len(action) == 1:
        globals()[action[0]]()
    else:
        print "Error: ambiguous parameters"
        usage()


if __name__ == '__main__':
    import getopt
    import sys
    main()
