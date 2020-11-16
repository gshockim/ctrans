#!/usr/bin/env python
# -*- coding: utf-8 -*-
# using Python 2.7!
# translates comments in code
# google translate portions are cleaned up from
#   http://www.halotis.com/2009/09/15/google-translate-api-python-script/
# everything else written by Kyle Isom <coder@kyleisom.net>
# usage:
#   ./ctrans.py -s filename
#       will translate a single file

# Updated 2020-03-02 by William Cable to use Google Cloud Translation 
#   because the old ajax api wasn't working anymore

# Setup Cloud Console project and download credentials
#   https://cloud.google.com/translate/docs/basic/setup-basic
# set path to credentials:
#   $env:GOOGLE_APPLICATION_CREDENTIALS="B:\AWI\Python\ctrans\Python Translate-50994b9b6934.json"

# pip install chardet multiprocessing simplejson google-cloud-translate

import chardet
import codecs
import getopt
import multiprocessing
import os
import re
import sys
import urllib
import simplejson

from google.cloud import translate_v2 as G_translate
translate_client = G_translate.Client()

### globals ###
 
# variables from halotis' code
lang        = 'en'  #Target Language
lang_src    = ''    #Source Language, leave empty for auto-detect

# misc vars
trace       = False                                 # enable debugging output
ext         = '.'+lang                             # extension of translated
                                                    # files
num_procs   =   32                                  # number of concurrent
                                                    # processes
                                                    
# coding vars                                                    
encodeas    = 'utf-8'                               # input file type
decodeas    = 'utf-8'                               # output file type
cerr        = 'strict'                              # what do with codec errors
autodetect  = True                                 # autodetect file encoding
transalate_string_literals = False
keep_original_text = False


def get_splits(text, splitLength = 4500):
    """
    Translate Api has a limit on length of text(4500 characters) that can be
    translated at once, 
    """
    
    return (text[index:index + splitLength]
            for index in xrange(0, len(text), splitLength))
 

def translate(text, target = None, source = lang_src):
    """
    Translate using Googles API
    """

    global lang

    if target is None:
        target = lang

    retText = ''
    
    for text in get_splits(text):
            if trace: print '[+] translation requested...'
            sys.stdout.flush()
            
            resp = translate_client.translate(
                text, target_language=target, source_language=source)

            text = text.rstrip('\r\n')

            try:
                    if text != resp['translatedText'] and keep_original_text:
                        retText += text+'('+resp['translatedText']+')'
                    else:
                        retText += resp['translatedText']
            except:
                    retText += text.decode('')
            if trace: print '\treceived!'
    return retText

### start kyle's code ###

## handle C-style comments

# handles /* \w+ */ comments
def trans_block_comment(comment):
    # comment should be arrive as a re.Match object, need to grab the group
    trans = unicode(comment.group())
    trans   = trans.lstrip('/*')
    trans   = trans.rstrip('*/')
    trans = trans.split('\n')
    # trans.split('\n') left '\r' in windows
    trans   = [ line.replace('\r', '') for line in trans ]

    print trans
    
    # translate each line and compensate for the fact that gtrans eats your
    # formatting
    trans   = [ translate(line) for line in trans ]
    comment = u'\n'.join(trans)
    comment = u'/*%s*/' % comment

    # here's your stupid translation    
    return comment

# handle // \w+ comments
def trans_line_comment(comment):
    trans = unicode(comment.group())
    if trace: print trans.encode('utf-8')
    trans   = trans.lstrip('//')
    trans   = translate(trans.strip())
    comment = u'// %s' % trans
    
    return comment


## handle non-C-style comments

# handle an initial '#', like in perl or python or your mom
def trans_scripting_comment(comment):
    trans   = unicode(comment.group())
    
    if trans.startswith('#!'): return trans
    
    trans   = trans.lstrip('#')
    trans   = translate(trans.strip())
    comment = '# %s' % trans
    
    return comment

# handle an initial '#', like in perl or python or your mom
def trans_lua_comment(comment):
    trans   = unicode(comment.group())
    
    trans   = trans.lstrip('--')
    trans   = translate(trans.strip())
    comment = '-- %s' % trans
    
    return comment

# handles "\w+"" string literals
def trans_block_string_literals(comment):
    # comment should be arrive as a re.Match object, need to grab the group
    trans = unicode(comment.group())
    trans   = trans.lstrip('"')
    trans   = trans.rstrip('"')

    trans = trans.split('\n')
    trans   = [ line.replace('\r', '') for line in trans ]

    # translate each line and compensate for the fact that gtrans eats your
    # formatting
    trans   = [ translate(line) for line in trans ]

    comment = u'\n'.join(trans)
    comment = u'"%s"' % comment
    
    # here's your stupid translation    
    return comment

# extensions for valid source files
source_exts     = { 
    'c-style':[ 'c', 'cpp', 'cc', 'h', 'hpp', 'js', 'ts' ],
    'script': [ 'py', 'pl', 'rb' ],
    'lua': ['lua']
}

# regex and process functions for each extensions
regex_comments = {
    'c-style': [
        { # string literals
            'string_literal': True,
            'regex': re.compile(r'"([\s\S]*?)"', re.M & re.U),
            'handler' : trans_block_string_literals
        },
        { # /*  */ comments
            'regex': re.compile(r'/\*([\s\S]*?)\*/', re.M & re.U),
            'handler' : trans_block_comment
        },
        { # // comments
            'regex': re.compile(r'//(.+)', re.U & re.M),
            'handler' : trans_line_comment
        }
    ],
    'script': [
        { # string literals
            'string_literal': True,
            'regex': re.compile(r'"([\s\S]*?)"', re.M & re.U),
            'handler' : trans_block_string_literals
        },
        { # # comments
            'regex': re.compile(r'#\s*(.+)', re.U & re.M),
            'handler' : trans_scripting_comment
        }
    ],
    'lua': [
        { # string literals
            'string_literal': True,
            'regex': re.compile(r'"([\s\S]*?)"', re.M & re.U),
            'handler' : trans_block_string_literals
        },
        { # -- comments
            'regex': re.compile(r'\-\-\s*(.+)', re.U & re.M),
            'handler' : trans_lua_comment
        }
    ]
}

### processing code ###
# the following functions handle regexes, file tree walking and file I/O

# guess the encoding on a file
#   returns a string with the encoding if it is confident in its guess,
#       False otherwise
#   detection threshhold is confidence required to return an encoding
#
# design note: returns a string instead of globally modifying the encodeas var
# to support concurrency - the memory of duplicating a short string containing
# the encoding is low enough to not cause a performance hit and prevents the
# code from having to involve locking or shared memory.
def guess_encoding(filename, detection_threshold = 0.8, return_dict = False):
    if trace: print '[+] attempting to autodetect coding for %s' % filename
    try:
        f = open(filename, 'rb')
        guess = chardet.detect(f.read())
        f.close()
    except IOError, e:
        if trace: print '[!] error on file %s, skipping...' % filename
        print '\t(error returned was %s)' % str(e)
        if not return_tuple: return False
    
    confidence = '%0.1f' % guess['confidence']
    confidence = float(confidence)

    if confidence < detection_threshold:
        print '[!] too low of a confidence (%f) to guess coding for %s' % (
            guess['confidence'],
            filename
        )
        return False
    else:
        if trace:
            print '[+] detected coding %s for file %s (confidence: %0.2f)' % (
                                                    guess['encoding'],
                                                    filename,
                                                    guess['confidence']
                                                    )
        return guess['encoding'] if not return_dict else {
            'encoding': guess['encoding'],
            'confidence': guess['confidence'] }
    
    
# attempt to guess dir
def guess_dir(dir):
    walk        = os.walk(dir)
    codes       = { }
    codec_scan  = [ ]
    
    while True:
        try:
            (dirp, dirs, files)     = walk.next()
        except StopIteration, e:
            break
        else:
            codec_scan.extend([ os.path.join(dirp, file) for file in files
                                if has_extensions(os.path.join(dirp, file))])

    for file in codec_scan:
        guess = guess_encoding(file, return_dict=True)
        encoding, confidence = guess['encoding'], guess['confidence']
        
        if encoding in codes:
            codes[encoding] += confidence
        else:
            codes[encoding] = confidence
            
    return list(sorted(codes, key=lambda x: codes[x], reverse=True))[0]

    
# translate an individual file
def scan_file(filename):
    new_filename    = filename + ext
    
    # the reason we use a local variable for the encoding based on either
    # the guess_encoding() function or a copy of the encodeas global is
    # detailed more in the design note in the comments for guess_encoding -
    # the tl;dr is it solves some concurrency issues without incurring any
    # major penalties.
    if autodetect:
        encoding = guess_encoding(filename)
        if not encoding:
            print '[!] could not reliably determine encoding for %s' % filename
            print '\taborting!'
            return
    else:
        encoding = encodeas
    
    try:
        reader  = codecs.open(filename, 'r',            # read old source file
                              encoding=encoding, errors = 'replace')      
        ucode   = reader.read()                         # untranslated code
        writer  = codecs.open(new_filename, 'w',        # write translated
                              encoding=decodeas)
        reader.close()
    except IOError, e:                                  # abort on IO error
        print '[!] error on file %s, skipping...' % filename
        print '\t(error returned was %s)' % str(e)
        return None

    if not ucode: return None

    regexs = get_regexs_by_extensions(filename)

    tcode = ucode
    for t in regexs:
        if transalate_string_literals is False and 'string_literal' in t and t['string_literal'] is True: continue
        tcode       = t['regex'].sub(t['handler'], tcode)
    
    writer.write(tcode)
    
    print '[+] translated %s to %s...' % (filename, new_filename)

# look through a directory
def scan_dir(dirname):
    global autodetect                   # used to tweak better file encoding
    global encodeas                     # scans
    
    scanner         = os.walk(dirname, topdown=True)
    pool            = multiprocessing.Pool(processes = num_procs)
    file_list       = []
    
    if autodetect:
        encodeas    = guess_dir(dirname)
        autodetect  = False
    
    while True:
        try:
            scan_t = scanner.next()   # scan_t: (dirp, dirs, files)
            print scan_t
        except StopIteration:
            break
        else:
            for f in scan_t[2]:
                file_list.append(os.path.join(scan_t[0], f))

    print file_list

    scan_list   = [ file for file in file_list
                    if has_extensions(file) ]
    
    dev = 1

    for filename in scan_list:
        scan_file(filename)

    pool.close()
    pool.join()


def has_extensions(filename):
    extension   = re.sub('^.+\\.(\\w+)$', '\\1', filename)
    for key, value in source_exts.iteritems():
        if extension in value: return True

# get regex, processor sets by extensions 
def get_regexs_by_extensions(filename):
    extension   = re.sub('^.+\\.(\\w+)$', '\\1', filename)
    for key, value in source_exts.iteritems():
        if extension in value: return regex_comments[key]

# set target language and generated file extentions for it
def set_lang(lang_code):
    print 'language: ' + lang_code
    lang = lang_code
    ext = '.'+lang

##### start main code #####
if __name__ == '__main__':
    (opts, args)    = getopt.getopt(sys.argv[1:], 's:d:e:o:t', 
                ['lang=', 'keep_source', 'string_literals'])
    dir_mode        = False
    target          = None
    
    for (opt, arg) in opts:
        if opt == '-s':
            dir_mode    = False
            target      = arg
        if opt == '-d':
            dir_mode    = True
            target      = arg
        if opt == '-e':
            if not arg == 'auto':
                encodeas = arg
            else:
                autodetect = True
        if opt == '-o':
            decodeas = arg
        if opt == '--keep_source':
            keep_original_text = True
        if opt == '--string_literals':
            transalate_string_literals = True
        if opt == '--lang':
            set_lang(arg)
    
    if dir_mode:
        scan_dir(target)
    else:
        scan_file(target)
