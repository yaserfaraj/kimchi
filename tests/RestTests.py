#
# Project Burnet
#
# Copyright IBM, Corp. 2013
#
# Authors:
#  Adam Litke <agl@linux.vnet.ibm.com>
#
# This work is licensed under the terms of the GNU GPLv2.
# See the COPYING file in the top-level directory.

import unittest
import json

import burnet.mockmodel
import burnet.server
from utils import *

test_server = None
model = None
host = None
port = None

#utils.silence_server()


def setUpModule():
    global test_server, model, host, port

    model = burnet.mockmodel.MockModel()
    host = '127.0.0.1'
    port = get_free_port()
    test_server = run_server(host, port, test_mode=True, model=model)


def tearDownModule():
    test_server.stop()


class RestTests(unittest.TestCase):
    def setUp(self):
        model.reset()

    def assertHTTPStatus(self, code, *args):
        resp = request(*args)
        self.assertEquals(code, resp.status)

    def assertValidJSON(self, txt):
        try:
            json.loads(txt)
        except ValueError:
            self.fail("Invalid JSON: %s" % txt)

    def test_404(self):
        """
        A non-existent path should return HTTP:404
        """
        url_list = ['/doesnotexist', '/vms/blah']
        for url in url_list:
            self.assertHTTPStatus(404, host, port, url)

    def test_wrong_method(self):
        """
        Using the wrong HTTP method should return HTTP:405
        """
        self.assertHTTPStatus(405, host, port, "/", None, 'DELETE')

    def test_accepts(self):
        """
        Verify the following expectations regarding the client Accept header:
          If omitted, default to html
          If 'application/json', serve the rest api
          If 'text/html', serve the UI
          If both of the above (in any order), serve the rest api
          If neither of the above, HTTP:406
        """
        resp = request(host, port, "/", headers={})
        self.assertTrue('<!doctype html>' in resp.read().lower())

        resp = request(host, port, "/", headers={'Accept': 'application/json'})
        self.assertValidJSON(resp.read())

        resp = request(host, port, "/", headers={'Accept': 'text/html'})
        self.assertTrue('<!doctype html>' in resp.read().lower())

        resp = request(host, port, "/",
                       headers={'Accept': 'application/json, text/html'})
        self.assertValidJSON(resp.read())

        resp = request(host, port, "/",
                       headers={'Accept': 'text/html, application/json'})
        self.assertValidJSON(resp.read())

        h = {'Accept': 'text/plain'}
        self.assertHTTPStatus(406, host, port, "/", None, 'GET', h)

    def test_parse_error(self):
        """
        Request parse errors should return HTTP:400
        """
        self.assertHTTPStatus(400, host, port, "/vms", '{', 'POST')

    def test_missing_required_parameter(self):
        """
        When a POST request is missing a required parameter, HTTP:400 should be
        returned, never HTTP:500.
        """
        url_list = ['/vms']
        req = json.dumps({})
        for url in url_list:
            self.assertHTTPStatus(400, host, port, url, req, 'POST')

    def test_get_vms(self):
        vms = json.loads(request(host, port, '/vms').read())
        self.assertEquals(0, len(vms))

        # Now add a couple of VMs to the mock model
        for i in xrange(10):
            name = 'vm-%i' % i
            req = json.dumps({'name': name, 'memory': 1024})
            resp = request(host, port, '/vms', req, 'POST')
            self.assertEquals(201, resp.status)

        vms = json.loads(request(host, port, '/vms').read())
        self.assertEquals(10, len(vms))

        vm = json.loads(request(host, port, '/vms/vm-1').read())
        self.assertEquals('vm-1', vm['name'])
        self.assertEquals('shutoff', vm['state'])

    def test_vm_lifecycle(self):
        # Create a VM
        req = json.dumps({'name': 'test-vm', 'memory': 128})
        resp = request(host, port, '/vms', req, 'POST')
        self.assertEquals(201, resp.status)

        # Verify the VM
        vm = json.loads(request(host, port, '/vms/test-vm').read())
        self.assertEquals('shutoff', vm['state'])

        # Test screenshot
        resp = request(host, port, vm['screenshot'], method='HEAD')
        self.assertEquals(200, resp.status)
        self.assertTrue(resp.getheader('Content-type').startswith('image'))

        # Start the VM
        resp = request(host, port, '/vms/test-vm/start', '{}', 'POST')
        vm = json.loads(request(host, port, '/vms/test-vm').read())
        self.assertEquals('running', vm['state'])

        # Force stop the VM
        resp = request(host, port, '/vms/test-vm/stop', '{}', 'POST')
        vm = json.loads(request(host, port, '/vms/test-vm').read())
        self.assertEquals('shutoff', vm['state'])

        # Delete the VM
        resp = request(host, port, '/vms/test-vm', '{}', 'DELETE')
        self.assertEquals(204, resp.status)

    def test_get_storagepools(self):
        storagepools = json.loads(request(host, port, '/storagepools').read())
        self.assertEquals(0, len(storagepools))

        # Now add a couple of StoragePools to the mock model
        for i in xrange(5):
            name = 'storagepool-%i' % i
            req = json.dumps({'name': name,
                              'capacity': 1024,
                              'allocated': 512,
                              'path': '/var/lib/libvirt/images/%i' % i,
                              'type': 'dir'})
            resp = request(host, port, '/storagepools', req, 'POST')
            self.assertEquals(201, resp.status)

        storagepools = json.loads(request(host, port, '/storagepools').read())
        self.assertEquals(5, len(storagepools))

        storagepool = json.loads(request(host, port,
                                '/storagepools/storagepool-1').read())
        self.assertEquals('storagepool-1', storagepool['name'])
        self.assertEquals('inactive', storagepool['state'])

    def test_storagepool_action(self):
        # Create a storage pool
        req = json.dumps({'name': 'test-pool',
                          'capacity': 1024,
                          'allocated': 512,
                          'path': '/var/lib/libvirt/images/',
                          'type': 'dir'})
        resp = request(host, port, '/storagepools', req, 'POST')
        self.assertEquals(201, resp.status)

        # Verify the storage pool
        storagepool = json.loads(request(host, port,
                        '/storagepools/test-pool').read())
        self.assertEquals('inactive', storagepool['state'])

        # activate the storage pool
        resp = request(host, port,
                       '/storagepools/test-pool/activate', '{}', 'POST')
        storagepool = json.loads(request(host, port,
                        '/storagepools/test-pool').read())
        self.assertEquals('active', storagepool['state'])

        # Deactivate the storage pool
        resp = request(host, port,
                       '/storagepools/test-pool/deactivate', '{}', 'POST')
        storagepool = json.loads(request(host, port,
                                '/storagepools/test-pool').read())
        self.assertEquals('inactive', storagepool['state'])

        # Delete the storage pool
        resp = request(host, port, '/storagepools/test-pool', '{}', 'DELETE')
        self.assertEquals(204, resp.status)

    def test_get_storagevolumes(self):
        # Now add a StoragePool to the mock model
        self._create_pool('pool-1')

        # Now add a couple of storage volumes to the mock model
        for i in xrange(5):
            name = 'volume-%i' % i
            req = json.dumps({'name': name,
                              'capacity': 1024,
                              'allocation': 512,
                              'type': 'disk',
                              'format': 'raw'})
            resp = request(host, port, '/storagepools/pool-1/storagevolumes',
                           req, 'POST')
            self.assertEquals(201, resp.status)

        storagevolumes = json.loads(request(host, port,
                                '/storagepools/pool-1/storagevolumes').read())
        self.assertEquals(5, len(storagevolumes))

        storagevolume = json.loads(request(host, port,
                    '/storagepools/pool-1/storagevolumes/volume-1').read())
        self.assertEquals('volume-1', storagevolume['name'])
        self.assertEquals('raw', storagevolume['format'])

        # Now remove the StoragePool from mock model
        self._delete_pool('pool-1')

    def test_storagevolume_action(self):
        # Now add a storage pool to the mock model
        self._create_pool('pool-2')
        # Create a storage volume
        req = json.dumps({'name': 'test-volume',
                          'capacity': 1024,
                          'allocation': 512,
                          'type': 'disk',
                          'format': 'raw'})
        resp = request(host, port,
                       '/storagepools/pool-2/storagevolumes/', req, 'POST')
        self.assertEquals(201, resp.status)

        # Verify the storage volume
        storagevolume = json.loads(request(host, port,
                    '/storagepools/pool-2/storagevolumes/test-volume').read())
        self.assertEquals('raw', storagevolume['format'])

        # Resize the storage volume
        req = json.dumps({'size': 768})
        resp = request(host, port,
                    '/storagepools/pool-2/storagevolumes/test-volume/resize',
                    req, 'POST')
        storagevolume = json.loads(request(host, port,
                    '/storagepools/pool-2/storagevolumes/test-volume').read())
        self.assertEquals(768, storagevolume['capacity'])

        # Wipe the storage volume
        resp = request(host, port,
                    '/storagepools/pool-2/storagevolumes/test-volume/wipe',
                    '{}', 'POST')
        storagevolume = json.loads(request(host, port,
                    '/storagepools/pool-2/storagevolumes/test-volume').read())
        self.assertEquals(0, storagevolume['allocation'])

        # Delete the storage volume
        resp = request(host, port,
                    '/storagepools/pool-2/storagevolumes/test-volume',
                    '{}', 'DELETE')
        self.assertEquals(204, resp.status)

        # Now remove the StoragePool from mock model
        self._delete_pool('pool-2')

    def _create_pool(self, name):
        req = json.dumps({'name': name,
                          'capacity': 10240,
                          'allocated': 5120,
                          'path': '/var/lib/libvirt/images/',
                          'type': 'dir'})
        resp = request(host, port, '/storagepools', req, 'POST')
        self.assertEquals(201, resp.status)

        # Verify the storage pool
        storagepool = json.loads(request(host, port,
                        '/storagepools/%s' % name).read())
        self.assertEquals('inactive', storagepool['state'])
        return name

    def _delete_pool(self, name):
        # Delete the storage pool
        resp = request(host, port, '/storagepools/%s' % name, '{}', 'DELETE')
        self.assertEquals(204, resp.status)

    def test_templates(self):
        resp = request(host, port, '/templates')
        self.assertEquals(200, resp.status)
        self.assertEquals(0, len(json.loads(resp.read())))

        # Create a template
        req = json.dumps({'name': 'test', 'os_distro': 'ImagineOS',
                          'os_version': 1.0})
        resp = request(host, port, '/templates', req, 'POST')
        self.assertEquals(201, resp.status)

        # Verify the template
        t = json.loads(request(host, port, '/templates/test').read())
        self.assertEquals('test', t['name'])
        self.assertEquals('ImagineOS', t['os_distro'])
        self.assertEquals(1.0, t['os_version'])
        self.assertEquals(1024, t['memory'])

        # Delete the template
        resp = request(host, port, '/templates/test', '{}', 'DELETE')
        self.assertEquals(204, resp.status)
