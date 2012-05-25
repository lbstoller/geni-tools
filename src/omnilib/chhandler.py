#!/usr/bin/python

#----------------------------------------------------------------------
# Copyright (c) 2012 Raytheon BBN Technologies
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and/or hardware specification (the "Work") to
# deal in the Work without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Work, and to permit persons to whom the Work
# is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Work.
#
# THE WORK IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE WORK OR THE USE OR OTHER DEALINGS
# IN THE WORK.
#----------------------------------------------------------------------
"""
Omni Clearinghouse call handler
Handle calls to clearinghouse functions, dispatching to the right
framework as necessary.
Also based on invocation mode, skip experimenter checks of inputs/outputs.
"""

import dateutil.parser

from omnilib.util import OmniError
from omnilib.util.dossl import _do_ssl
import omnilib.util.credparsing as credutils
import omnilib.util.handler_utils
from omnilib.util.handler_utils import _get_slice_cred, _listaggregates, _print_slice_expiration

class CHCallHandler(object):
    """
    Omni Clearinghouse call handler
    Handle calls to clearinghouse functions, dispatching to the right
    framework as necessary.
    Also based on invocation mode, skip experimenter checks of inputs/outputs.
    """

    def __init__(self, framework, config, opts):
        self.framework = framework
        self.logger = config['logger']
        self.omni_config = config['omni']
        self.config = config
        self.opts = opts
        if self.opts.abac:
            aconf = self.config['selected_framework']
            if 'abac' in aconf and 'abac_log' in aconf:
                self.abac_dir = aconf['abac']
                self.abac_log = aconf['abac_log']
            else:
                self.logger.error("ABAC requested (--abac) and no abac= or abac_log= in omni_config: disabling ABAC")
                self.opts.abac= False
                self.abac_dir = None
                self.abac_log = None

    def _raise_omni_error( self, msg, err=OmniError ):
        self.logger.error( msg )
        raise err, msg

    def _handle(self, args):
        if len(args) == 0:
            self._raise_omni_error('Insufficient number of arguments - Missing command to run')
        
        call = args[0].lower()
        # disallow calling private methods
        if call.startswith('_'):
            return
        if not hasattr(self,call):
            self._raise_omni_error('Unknown function: %s' % call)
        return getattr(self,call)(args[1:])

    def listaggregates(self, args):
        """Print the known aggregates' URN and URL
        Gets aggregates from:
        - command line (one, no URN available), OR
        - command line nickname (one, URN may be supplied), OR
        - omni_config (1+, no URNs available), OR
        - Specified control framework (via remote query).
        This is the aggregates that registered with the framework.
        """
        retStr = ""
        retVal = {}
        (aggs, message) = _listaggregates(self)
        aggList = aggs.items()
        self.logger.info("Listing %d aggregates..."%len(aggList))
        aggCnt = 0
        for (urn, url) in aggList:
            aggCnt += 1
            self.logger.info( "  Aggregate %d:\n \t%s \n \t%s" % (aggCnt, urn, url) )
#            retStr += "%s: %s\n" % (urn, url)
            retVal[urn] = url
        if aggs == {} and message != "":
            retStr += ("No aggregates found: %s" % message)
        elif len(aggList)==0:
            retStr = "No aggregates found."
        elif len(aggList) == 1:
            retStr = "Found 1 aggregate. URN: %s; URL: %s" % (retVal.keys()[0], retVal[retVal.keys()[0]])
        else:
            retStr = "Found %d aggregates." % len(aggList)
        return retStr, retVal

    def createslice(self, args):
        """Create a Slice at the given Slice Authority.
        Arg: slice name
        Slice name could be a full URN, but is usually just the slice name portion.
        Note that PLC Web UI lists slices as <site name>_<slice name>
        (e.g. bbn_myslice), and we want only the slice name part here (e.g. myslice).

        To create the slice and save off the slice credential:
           omni.py -o createslice myslice
        To create the slice and save off the slice credential to a specific file:
           omni.py -o --slicecredfile mySpecificfile-myslice-credfile.xml
                   createslice myslice

        Note that Slice Authorities typically limit this call to privileged
        users, e.g. PIs.

        Note also that typical slice lifetimes are short. See RenewSlice.
        """
        retVal = ""
        if len(args) == 0 or args[0] == None or args[0].strip() == "":
            self._raise_omni_error('createslice requires arg of slice name')

        name = args[0]

        # FIXME: catch errors getting slice URN to give prettier error msg?
        urn = self.framework.slice_name_to_urn(name)
        
        (slice_cred, message) = _do_ssl(self.framework, None, "Create Slice %s" % urn, self.framework.create_slice, urn)
        if slice_cred:
            slice_exp = credutils.get_cred_exp(self.logger, slice_cred)
            printStr = "Created slice with Name %s, URN %s, Expiration %s" % (name, urn, slice_exp) 
            retVal += printStr+"\n"
            self.logger.info( printStr )
            filename = self._maybe_save_slicecred(name, slice_cred)
            if filename is not None:
                prstr = "Wrote slice %s credential to file '%s'" % (name, filename)
                retVal += prstr + "\n"
                self.logger.info(prstr)

            success = urn

        else:
            printStr = "Create Slice Failed for slice name %s." % (name) 
            if message != "":
                printStr += " " + message
            retVal += printStr+"\n"
            self.logger.error( printStr )
            success = None
            if not self.logger.isEnabledFor(logging.DEBUG):
                self.logger.warn( "   Try re-running with --debug for more information." )
        return retVal, success
        
    def renewslice(self, args):
        """Renew the slice at the clearinghouse so that the slivers can be
        renewed.
        Args: slicename, and expirationdate
          Note that Slice Authorities may interpret dates differently if you do not
          specify a timezone. SFA drops any timezone information though.
        Slice name could be a full URN, but is usually just the slice name portion.
        Note that PLC Web UI lists slices as <site name>_<slice name>
        (e.g. bbn_myslice), and we want only the slice name part here (e.g. myslice).

        Return summary string, new slice expiration (string)
        """
        if len(args) != 2 or args[0] == None or args[0].strip() == "":
            self._raise_omni_error('renewslice missing args: Supply <slice name> <expiration date>')
        name = args[0]
        expire_str = args[1]

        # convert the slice name to a framework urn
        # FIXME: catch errors getting slice URN to give prettier error msg?
        urn = self.framework.slice_name_to_urn(name)

        # convert the desired expiration to a python datetime
        try:
            in_expiration = dateutil.parser.parse(expire_str)
        except:
            msg = 'Unable to parse date "%s".\nTry "YYYYMMDDTHH:MM:SSZ" format'
            msg = msg % (expire_str)
            self._raise_omni_error(msg)

        # Try to renew the slice
        (out_expiration, message) = _do_ssl(self.framework, None, "Renew Slice %s" % urn, self.framework.renew_slice, urn, in_expiration)

        if out_expiration:
            prtStr = "Slice %s now expires at %s UTC" % (name, out_expiration)
            self.logger.info( prtStr )
            retVal = prtStr+"\n"
            retTime = out_expiration
        else:
            prtStr = "Failed to renew slice %s" % (name)
            if message != "":
                prtStr += ". " + message
            self.logger.warn( prtStr )
            retVal = prtStr+"\n"
            retTime = None
        retVal +=_print_slice_expiration(self, urn)
        return retVal, retTime

    def deleteslice(self, args):
        """Framework specific DeleteSlice call at the given Slice Authority
        Arg: slice name
        Slice name could be a full URN, but is usually just the slice name portion.
        Note that PLC Web UI lists slices as <site name>_<slice name>
        (e.g. bbn_myslice), and we want only the slice name part here (e.g. myslice).

        Delete all your slivers first!
        This does not free up resources at various aggregates.
        """
        if len(args) == 0 or args[0] == None or args[0].strip() == "":
            self._raise_omni_error('deleteslice requires arg of slice name')

        name = args[0]

        # FIXME: catch errors getting slice URN to give prettier error msg?
        urn = self.framework.slice_name_to_urn(name)

        (res, message) = _do_ssl(self.framework, None, "Delete Slice %s" % urn, self.framework.delete_slice, urn)
        # return True if successfully deleted slice, else False
        if (res is None) or (res is False):
            retVal = False
        else:
            retVal = True
        prtStr = "Delete Slice %s result: %r" % (name, res)
        if res is None and message != "":
            prtStr += ". " + message
        self.logger.info(prtStr)
        return prtStr, retVal

    def listmyslices(self, args):
        """Provides a list of slices of user provided as first argument.
        Not supported by all frameworks."""
        if len(args) > 0:
            username = args[0].strip()
        else:
            self._raise_omni_error('listmyslices requires 1 arg: user')

        retStr = ""
        (slices, message) = _do_ssl(self.framework, None, "List Slices from Slice Authority", self.framework.list_my_slices, username)
        if slices is None:
            # only end up here if call to _do_ssl failed
            slices = []
            self.logger.error("Failed to list slices for user '%s'"%(username))
            retStr += "Server error: %s. " % message
        elif len(slices) > 0:
            self.logger.info("User '%s' has slice(s): \n\t%s"%(username,"\n\t".join(slices)))
        else:
            self.logger.info("User '%s' has NO slices."%username)

        # summary
        retStr += "Found %d slice(s) for user '%s'.\n"%(len(slices), username)

        return retStr, slices

    def listmykeys(self, args):
        """Provides a list of SSH public keys registered at the CH for the current user.
        Not supported by all frameworks."""

        retStr = ""
        (keys, message) = _do_ssl(self.framework, None, "List Keys from Slice Authority", self.framework.list_my_ssh_keys)
        if keys is None:
            # only end up here if call to _do_ssl failed
            keys = []
            self.logger.error("Failed to list keys for you")
            retStr += "Server error: %s. " % message
        elif len(keys) > 0:
            self.logger.info("User has key(s): \n\t%s"%("\n\t".join(keys)))
        else:
            self.logger.info("User has NO keys.")

        # summary
        retStr += "Found %d key(s) for user.\n"%(len(keys))

        return retStr, keys

    def getusercred(self, args):
        """Save your user credential to <framework nickname>-usercred.xml
        Useful for debugging."""
        (cred, message) = self.framework.get_user_cred()
        
        if cred is None:
            self._raise_omni_error("Got no user credential from framework: %s" % message)
        fname = self.opts.framework + "-usercred.xml"
        self.logger.info("Writing your user credential to %s" % fname)
        with open(fname, "wb") as file:
            file.write(cred)
        self.logger.info("User credential:\n%r", cred)
        return "Saved user credential to %s" % fname, cred

    def getslicecred(self, args):
        """Get the AM API compliant slice credential (signed XML document).

        If you specify the -o option, the credential is saved to a file.
        The filename is <slicename>-cred.xml
        But if you specify the --slicecredfile option then that is the
        filename used.

        Additionally, if you specify the --slicecredfile option and that
        references a file that is not empty, then we do not query the Slice
        Authority for this credential, but instead read it from this file.

        e.g.:
          Get slice mytest credential from slice authority, save to a file:
            omni.py -o getslicecred mytest
          
          Get slice mytest credential from slice authority, save to a file with prefix mystuff:
            omni.py -o -p mystuff getslicecred mytest

          Get slice mytest credential from slice authority, save to a file with name mycred.xml:
            omni.py -o --slicecredfile mycred.xml getslicecred mytest

          Get slice mytest credential from saved file (perhaps a delegated credential?) delegated-mytest-slicecred.xml:
            omni.py --slicecredfile delegated-mytest-slicecred.xml getslicecred mytest

        Arg: slice name
        Slice name could be a full URN, but is usually just the slice name portion.
        Note that PLC Web UI lists slices as <site name>_<slice name>
        (e.g. bbn_myslice), and we want only the slice name part here (e.g. myslice).
        """

        if len(args) == 0 or args[0] == None or args[0].strip() == "":
            # could print help here but that's verbose
            #parse_args(None)
            self._raise_omni_error('getslicecred requires arg of slice name')

        name = args[0]

        # FIXME: catch errors getting slice URN to give prettier error msg?
        urn = self.framework.slice_name_to_urn(name)
        (cred, message) = _get_slice_cred(self, urn)

        if cred is None:
            retVal = "No slice credential returned for slice %s: %s"%(urn, message)
            return retVal, None

        # Log if the slice expires soon
        _print_slice_expiration(self, urn, cred)

        # Print the non slice cred bit to log stream so
        # capturing just stdout gives just the cred hopefully
        self.logger.info("Retrieved slice cred for slice %s", urn)
#VERBOSE ONLY        self.logger.info("Slice cred for slice %s", urn)
#VERBOSE ONLY        self.logger.info(cred)
#        print cred

        retVal = cred
        retItem = cred
        filename = self._maybe_save_slicecred(name, cred)
        if filename is not None:
            self.logger.info("Wrote slice %s credential to file '%s'" % (name, filename))
            retVal = "Saved slice %s cred to file %s" % (name, filename)

        return retVal, retItem

    def print_slice_expiration(self, args):
        """Print the expiration time of the given slice, and a warning
        if it is soon.
        Arg: slice name
        Slice name could be a full URN, but is usually just the slice name portion.
        Note that PLC Web UI lists slices as <site name>_<slice name>
        (e.g. bbn_myslice), and we want only the slice name part here (e.g. myslice).
        """

        if len(args) == 0 or args[0] == None or args[0].strip() == "":
            # could print help here but that's verbose
            #parse_args(None)
            self._raise_omni_error('print_slice_expiration requires arg of slice name')

        name = args[0]

        # FIXME: catch errors getting slice URN to give prettier error msg?
        urn = self.framework.slice_name_to_urn(name)
        (cred, message) = _get_slice_cred(self, urn)

        retVal = None
        if cred is None:
            retVal = "No slice credential returned for slice %s: %s"%(urn, message)
            return retVal, None

        # Log if the slice expires soon
        retVal = _print_slice_expiration(self, urn, cred)
        return retVal, retVal

#########
## Helper functions follow

    def _maybe_save_slicecred(self, name, slicecred):
        """Save slice credential to a file, returning the filename or
        None on error or config not specifying -o

        Only saves if self.opts.output and non-empty credential

        If you didn't specify -o but do specify --tostdout, then write
        the slice credential to STDOUT

        Filename is:
        --slicecredfile if supplied
        else [<--p value>-]-<slicename>-cred.xml
        """
        if name is None or name.strip() == "" or slicecred is None or slicecred.strip() is None:
            return None

        filename = None
        if self.opts.output:
            if self.opts.slicecredfile:
                filename = self.opts.slicecredfile
            else:
                filename = name + "-cred.xml"
                if self.opts.prefix and self.opts.prefix.strip() != "":
                    filename = self.opts.prefix.strip() + "-" + filename
            with open(filename, 'w') as file:
                file.write(slicecred + "\n")
        elif self.opts.tostdout:
            self.logger.info("Writing slice %s cred to STDOUT per options", name)
            print slicecred
        return filename
