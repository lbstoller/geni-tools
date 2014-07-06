#----------------------------------------------------------------------
# Copyright (c) 2012-2014 Raytheon BBN Technologies
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

# Base class and specific class for binding variables to support
# parameterized ABAC authorization

# These return bindings, which are a dictionary of {name : value}

import time
import gcf.sfa.trust.gid as gid
from gcf.geni.util.cred_util import CredentialVerifier
from .sfa_authorizer import SFA_Authorizer
import xml.dom.minidom
from .base_authorizer import AM_Methods


class Base_Binder:

    def __init__(self, root_cert):
        self._root_cert = root_cert

    def generate_bindings(self, method, caller, creds, args, opts, agg_mgr):
        return {}

    def handle_result(self, method, caller, args, options, result, agg_mgr):
        pass


# Define standard bindings of 
# $SLICE_URN, $PROJECT_URN, $CALLER, $CALLER_AUTHORITY, $METHOD
# $HOUR, $MONTH, $YEAR, $DAY_OF_WEEK
class Standard_Binder(Base_Binder):

    def __init__(self, root_cert):
        Base_Binder.__init__(self, root_cert)

    def generate_bindings(self, method, caller, creds, args, opts, agg_mgr):
        bindings = {}

        bindings['$METHOD'] = method

        caller_urn = gid.GID(string=caller).get_urn()
        bindings['$CALLER'] = caller_urn

        slice_urn = args['slice_urn']
        bindings['$SLICE_URN'] = slice_urn


        project_urn = convert_slice_urn_to_project_urn(slice_urn)
        bindings['$PROJECT_URN'] = project_urn

        caller_authority = convert_user_urn_to_authority_urn(caller_urn)
        bindings['$CALLER_AUTHORITY'] = caller_authority

        now = time.localtime()
        bindings['$HOUR'] = str(now.tm_hour)
        bindings['$MONTH'] = str(now.tm_mon)
        bindings['$YEAR'] = str(now.tm_year)
        bindings['$DAY_OF_WEEK'] = str(now.tm_wday)

        return bindings



class SFA_Binder(Base_Binder):

    def __init__(self, root_cert):
        Base_Binder.__init__(self, root_cert)
        self._cred_verifier = CredentialVerifier(root_cert)

    def generate_bindings(self, method, caller, creds, args, opts, agg_mgr):

        bindings = {}

        slice_urn = None
        if 'slice_urn' in args: slice_urn = args['slice_urn']

        privileges = SFA_Authorizer.METHOD_ATTRIBUTES[method]['privileges']

        try:
            new_creds = self._cred_verifier.verify_from_strings(caller, creds,
                                                                slice_urn, 
                                                                privileges,
                                                                opts)
            bindings["$SFA_AUTHORIZED"] = "True"
        except Exception, e:
            pass

        return bindings

# Bind $STITCH_POINTS to all points on hops requested 
# to be connected to this aggregate
class Stitching_Binder(Base_Binder):

    def __init__(self, root_cert):
        Base_Binder.__init__(self, root_cert)

    def generate_bindings(self, method, caller, creds, args, opts, agg_mgr):
        if method in [AM_Methods.CREATE_SLIVER_V2, AM_Methods.ALLOCATE_V3]:
            am_urn = agg_mgr._delegate._my_urn
            if 'rspec' not in args: return {}
            rspec_raw = args['rspec']
            rspec_doc = xml.dom.minidom.parseString(rspec_raw)
            rspec_elt = rspec_doc.getElementsByTagName('rspec')[0]
            stitching_elts = rspec_elt.getElementsByTagName('stitching')
            if len(stitching_elts) == 0: return {}
            stitching_elt = stitching_elts[0]
            link_elts = [elt for elt in rspec_elt.childNodes \
                             if elt.nodeType == elt.ELEMENT_NODE \
                             and elt.tagName == 'link']
            my_link_elts = []
            requested_stitch_points = []
            for link_elt in link_elts:
                for component_manager in \
                        link_elt.getElementsByTagName('component_manager'):
                    if component_manager.getAttribute('name') == am_urn:
                        my_link_elts.append(link_elt)
                        break
            my_link_ids = [link_elt.getAttribute('client_id') \
                               for link_elt in my_link_elts]
            my_paths = \
                [path for path in stitching_elt.getElementsByTagName('path') \
                     if path.getAttribute('id') in my_link_ids]
            for path in my_paths:
                path_link_ids = \
                    [link.getAttribute('id') \
                         for link in path.getElementsByTagName('link')]
                requested_stitch_points = \
                    requested_stitch_points + path_link_ids

            return {"$REQUESTED_STITCH_POINTS" : str(requested_stitch_points) }
        else:
            return {}

# Return caller_urn, slice_urn, project_urn, authority_urn
def _retrieve_context_urns(caller, args):
    slice_urn = None
    project_urn = None
    if 'slice_urn' in args:
        slice_urn = args['slice_urn']
        project_urn = convert_slice_urn_to_project_urn(slice_urn)
    caller_urn = gid.GID(string=caller).get_urn()
    authority_urn = convert_user_urn_to_authority_urn(caller_urn)
    return caller_urn, slice_urn, project_urn, authority_urn
    
def convert_slice_urn_to_project_urn(slice_urn):
    project_auth_token = slice_urn.split('+')[1]
    project_auth_parts = project_auth_token.split(':')
    project_auth = project_auth_parts[0]
    project_name = project_auth_parts[1]
    project_urn = _convert_urn(project_auth, 'project', project_name)
    return project_urn

def convert_user_urn_to_authority_urn(user_urn):
    user_auth_token = user_urn.split('+')[1]
    user_authority = _convert_urn(user_auth_token,'authority', 'ca')
    return user_authority

def _convert_urn(value, obj_type, obj_name):
    return 'urn:publicid:IDN+%s+%s+%s' % (value, obj_type, obj_name)

