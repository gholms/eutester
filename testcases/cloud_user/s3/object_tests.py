#!/usr/bin/env python

#
############################################
#                                          #
# objectstorage/S3 Object Test Cases       #
#                                          #
############################################


#Author: Zach Hill <zach@eucalyptus.com>
#Author: Vic Iglesias <vic@eucalyptus.com>

import time
import random

from boto.s3.key import Key
from boto.s3.prefix import Prefix
from boto.exception import S3ResponseError
import dateutil.parser

from eucaops import Eucaops
from eutester.eutestcase import EutesterTestCase
from eucaops import S3ops


class ObjectTestSuite(EutesterTestCase):
    data_size = 1000
    
    def __init__(self):
        self.setuptestcase()
        self.setup_parser()
        self.parser.add_argument("--s3endpoint", default=None)
        self.get_args()
        # Setup basic eutester object
        if self.args.s3endpoint:
            self.tester = S3ops( credpath=self.args.credpath, endpoint=self.args.endpoint)
        else:
            self.tester = Eucaops( credpath=self.args.credpath, config_file=self.args.config, password=self.args.password)
        
        self.bucket_prefix = "eutester-bucket-test-suite-" + str(int(time.time())) + "-"
        self.buckets_used = set()
        random.seed(time.time())
        self.test_bucket_name = self.bucket_prefix + str(random.randint(0,100))
        self.test_bucket = self.tester.create_bucket(self.test_bucket_name)
        self.buckets_used.add(self.test_bucket_name)
        #Create some test data for the objects
        self.test_object_data = ""
        for i in range(0, self.data_size):
            self.test_object_data += chr(random.randint(32,126))            
        print "Generated data for objects: " + self.test_object_data
        
    
    def print_key_info(self, keys=None):
        for key in keys:
            self.tester.info("Key=" + str(key.key) + " -- version= " + str(key.version_id) + " -- eTag= " + str(key.etag)
                             + " -- ACL= " + str(key.get_xml_acl()))
    
    def put_object(self, bucket=None, object_key=None, object_data=None):
        """Puts an object with the specified name and data in the specified bucket"""
        if bucket == None:
            raise Exception("Cannot put object without proper bucket reference")
        
        try :
            key = Key(bucket=bucket,name=object_key)
            key.set_contents_from_string(object_data)                        
            return key.etag
        except Exception as e:
            self.tester.info("Exception occured during 'PUT' of object " + object_key + " into bucket " + bucket.name + ": " + e.message)
            return None
        
     
    def enable_versioning(self, bucket):
        """Enable versioning on the bucket, checking that it is not already enabled and that the operation succeeds."""
        vstatus = bucket.get_versioning_status()
        if vstatus != None and len(vstatus.keys()) > 0 and vstatus['Versioning'] != None and vstatus['Versioning'] != 'Disabled':
            self.tester.info("Versioning status should be null/Disabled, found: " + vstatus['Versioning'])
            return False
        else:
            self.tester.info("Bucket versioning is Disabled")
        
        #Enable versioning
        bucket.configure_versioning(True)
        if bucket.get_versioning_status()['Versioning'] == 'Enabled':
            self.tester.info("Versioning status correctly set to enabled")
            return True
        else:
            self.tester.info("Versioning status not enabled, should be.")
            return False
        return False
    
    def suspend_versioning(self, bucket):
        """Suspend versioning on the bucket, checking that it is previously enabled and that the operation succeeds."""
        if bucket.get_versioning_status()['Versioning'] == 'Enabled':
            self.tester.info("Versioning status correctly set to enabled")
        else:
            self.tester.info("Versioning status not enabled, should be. Can't suspend if not enabled....")
            return False
    
        #Enable versioning
        bucket.configure_versioning(False)
        if bucket.get_versioning_status()['Versioning'] == 'Suspended':
            self.tester.info("Versioning status correctly set to suspended")
            return True
        else:
            self.tester.info("Versioning status not suspended.")
            return False
        return False 
             
    def check_version_listing(self, version_list, total_expected_length):
        """Checks a version listing for both completeness and ordering as well as pagination if required"""
        self.tester.info("Checking bucket version listing. Listing is " + str(len(version_list)) + " entries long")
        if total_expected_length >= 1000:
            assert(len(version_list) == 999)
        else:
            assert(len(version_list) == total_expected_length)
        
        prev_obj = None
        should_fail = None
        for obj in version_list:
            if isinstance(obj,Key):
                self.tester.info("Key: " + obj.name + " -- " + obj.version_id + "--" + obj.last_modified)                
                if prev_obj != None:
                    if self.compare_versions(prev_obj, obj) > 0:
                        should_fail = obj
                prev_obj = obj
            else:
                self.tester.info("Not a key, skipping: " + str(obj))
        return should_fail

    def compare_versions(self, key1, key2):
        """
        Returns -1 if key1 < key2, 0 if equal, and 1 if key1 > key2. 
        Compares names lexicographically, if equal, compares date_modified if versions are different. 
        If version_id and name are equal then key1 = key2
        If an error occurs or something is wrong, returns None
        """
        if key1.name < key2.name:
            #self.debug("Key1: " + key1.name + " is less than " + key2.name)
            return 1
        elif key1.name > key2.name:
            #self.debug("Key1: " + key1.name + " is greater than " + key2.name)
            return -1
        else:
            if key1.version_id == key2.version_id:
                #self.debug("Key1: " + key1.name + " is the same version as " + key2.name)
                return 0
            else:
                if dateutil.parser.parse(key1.last_modified) > dateutil.parser.parse(key2.last_modified):
                    #self.debug("Key1: " + key1.last_modified + " last modified is greater than " + key2.last_modified)
                    return 1
                elif dateutil.parser.parse(key1.last_modified) < dateutil.parser.parse(key2.last_modified):
                    #self.debug("Key1: " + key1.last_modified + " last modified is less than " + key2.last_modified)
                    return -1
        return None
    
    def test_object_basic_ops(self):
        """
        Tests basic operations on objects: simple GET,PUT,HEAD,DELETE.
        
        """
        self.tester.info("Basic Object Operations Test (GET/PUT/HEAD)")
        if self.test_bucket == None:
            self.fail("Error: test_bucket not set, cannot run test")
            
        #Test PUT & GET
        testkey="testkey1-" + str(int(time.time()))
        self.put_object(bucket=self.test_bucket, object_key=testkey, object_data=self.test_object_data)
        
        ret_key = self.test_bucket.get_key(testkey)
        ret_content = ret_key.get_contents_as_string()
        
        if ret_content == self.test_object_data:
            self.tester.info("Set content = get content, put passed")
        else:
            if ret_content != None:
                self.tester.info("Got content: " + ret_content)
            else:
                self.tester.info("No content returned")
            self.tester.info("Expected content: " + self.test_object_data)
            self.fail("Put content not the same as what was returned")
        
        #Test HEAD
        key_meta = self.test_bucket.get_key(testkey)
        if key_meta != ret_key:
            self.tester.info("Something is wrong, the HEAD operation returned different metadata than the GET operation")
        else:
            self.tester.info("HEAD meta = GET meta, all is good")
        
        #Test copy operation (GET w/source headers)
        new_key = "testkey2"
        self.test_bucket.copy_key(new_key, self.test_bucket_name,testkey)
        keylist = self.test_bucket.list()
        counter = 0
        for k in keylist:
            if isinstance(k, Prefix):
                self.tester.info("Prefix: " + "NULL" if k == None else k.name)
            else:
                self.tester.info("Key: " + k.name + " Etag: " + k.etag)
                counter += 1
        if counter != 2:
            self.fail("Expected 2 keys after copy operation, found only: " + len(keylist))
        try:
            ret_key = self.test_bucket.get_key(new_key)
        except:
            self.fail("Could not get object copy")
        if ret_key == None:
            self.fail("Could not get object copy")
            
        if self.test_bucket.get_key(testkey).get_contents_as_string() != ret_key.get_contents_as_string():
            self.fail("Contents of original key and copy don't match")
        else:
            self.tester.info("Copy key contents match original!")
        
        #Test DELETE
        self.test_bucket.delete_key(testkey)
        ret_key = None
        ret_key = self.test_bucket.get_key(testkey)
        if ret_key:
            self.tester.info("Erroneously got: " + ret_key.name)
            raise S3ResponseError(404, "Should have thrown exception for getting a non-existent object")
        self.tester.info("Finishing basic ops test")
               
    def test_object_byte_offset_read(self):
        """Tests fetching specific byte offsets of the object"""
        self.tester.info("Byte-range Offset GET Test")
        self.test_bucket = self.clear_and_rebuild_bucket(self.test_bucket_name)
        testkey = "rangetestkey-" + str(int(time.time()))
        source_bytes = bytearray(self.test_object_data)
        
        #Put the object initially
        self.put_object(bucket=self.test_bucket, object_key=testkey, object_data=self.test_object_data)
        
        #Test range for first 100 bytes of object
        print "Trying start-range object get"
        try:
            data_str = Key(bucket=self.test_bucket,name=testkey).get_contents_as_string(headers={"Range":"bytes=0-99"})
        except:
            self.fail("Failed range object get first 100 bytes")
        
        startrangedata = bytearray(data_str)        
        print "Got: " + startrangedata
        print "Expected: " + str(source_bytes[:100])
        start = 0        
        for i in range(0,100):
            if startrangedata[i-start] != source_bytes[i]:
                print "Byte: " + startrangedata[i] + " differs!"
                self.fail("Start-range Ranged-get failed")
            
        print "Trying mid-object range"   
        try: 
            data_str = Key(bucket=self.test_bucket,name=testkey).get_contents_as_string(headers={"Range":"bytes=500-599"})
        except:
            self.fail("Failed range object get for middle 100 bytes")     
        midrangedata = bytearray(data_str)
        start = 500
        for i in range(start,start+100):
            if midrangedata[i-start] != source_bytes[i]:
                print "Byte: " + midrangedata[i] + "differs!"
                self.fail("Mid-range Ranged-get failed")
        
        print "Trying end-range object get"
        #Test range for last 100 bytes of object
        try:
            data_str = Key(bucket=self.test_bucket,name=testkey).get_contents_as_string(headers={"Range":"bytes=800-899"})
        except:
            self.fail("Failed range object get for last 100 bytes")
            
        endrangedata = bytearray(data_str)
        print "Got: " + str(endrangedata)
        start = 800
        try:
            for i in range(start,start+100):
                if endrangedata[i-start] != source_bytes[i]:
                    print "Byte: " + endrangedata[i] + "differs!"
                    self.fail("End-range Ranged-get failed")
        except Exception as e:
            print "Exception! Received: " + e
        
        print "Range test complete"
        
    def test_object_post(self):
        """Test the POST method for putting objects, requires a pre-signed upload policy and url"""
        self.fail("Test not implemented")
                
    def test_object_large_objects(self):
        """Test operations on large objects (>1MB), but not so large that we must use the multi-part upload interface"""
        self.tester.info("Testing large-ish objects over 1MB in size on bucket" + self.test_bucket_name)
        self.test_bucket = self.clear_and_rebuild_bucket(self.test_bucket_name)
        test_data = ""
        large_obj_size_bytes = 5 * 1024 * 1024 #5MB
        self.tester.info("Generating " + str(large_obj_size_bytes) + " bytes of data")

        #Create some test data
        for i in range(0, large_obj_size_bytes):
            test_data += chr(random.randint(32,126))

        self.tester.info("Uploading object content of size: " + str(large_obj_size_bytes) + " bytes")        
        keyname = "largeobj-" + str(int(time.time()))
        self.put_object(bucket=self.test_bucket, object_key=keyname, object_data=test_data)
        self.tester.info("Done uploading object")

        ret_key = self.test_bucket.get_key(keyname)
        ret_data = ret_key.get_contents_as_string()
        
        if ret_data != test_data:
            self.fail("Fetched data and generated data don't match")
        else:
            self.tester.info("Data matches!")
        
        self.tester.info("Removing large object")
        self.test_bucket.delete_key(ret_key)
        self.tester.info("Complete large object test")
        pass
            
    def test_object_multipart(self):
        """Test the multipart upload interface"""
        self.fail("Feature not implemented")
        
    def test_object_versioning_enabled(self):
        """Tests object versioning for get/put/delete on a versioned bucket"""
        self.tester.info("Testing bucket Versioning-Enabled")
        self.test_bucket = self.clear_and_rebuild_bucket(self.test_bucket_name)
        if not self.enable_versioning(self.test_bucket):
            self.fail("Could not properly enable versioning")
             
        #Create some keys
        keyname = "versionkey-" + str(int(time.time()))
        
        #Multiple versions of the data
        v1data = self.test_object_data + "--version1"
        v2data = self.test_object_data + "--version2"
        v3data = self.test_object_data + "--version3"
        
        #Test sequence: put v1, get v1, put v2, put v3, get v3, delete v3, restore with v1 (copy), put v3 again, delete v2 explicitly
        self.put_object(bucket=self.test_bucket, object_key=keyname, object_data=v1data)
                
        #Get v1
        obj_v1 = self.test_bucket.get_key(keyname)
        self.tester.check_md5(eTag=obj_v1.etag,data=v1data)
        
        self.tester.info("Initial bucket state after object uploads without versioning:")
        self.print_key_info(keys=[obj_v1])
                
        #Put v2 (and get/head to confirm success)
        self.put_object(bucket=self.test_bucket, object_key=keyname,object_data=v2data)
        obj_v2 = self.test_bucket.get_key(keyname)
        self.tester.check_md5(eTag=obj_v2.etag,data=v2data)
        self.print_key_info(keys=[obj_v1, obj_v2])
        
        #Put v3 (and get/head to confirm success)
        self.put_object(bucket=self.test_bucket, object_key=keyname,object_data=v3data)
        obj_v3 = self.test_bucket.get_key(keyname)
        self.tester.check_md5(eTag=obj_v3.etag,data=v3data)
        self.print_key_info(keys=[obj_v1, obj_v2, obj_v3])
        
        #Get a specific version, v1
        v1_return = self.test_bucket.get_key(key_name=keyname,version_id=obj_v1.version_id)
        self.print_key_info(keys=[v1_return])
        
        #Delete current latest version (v3)
        self.test_bucket.delete_key(keyname)

        del_obj = self.test_bucket.get_key(keyname)
        if del_obj:
            self.tester.info("Erroneously got: " + del_obj.name)
            raise S3ResponseError(404, "Should have thrown this exception for getting a non-existent object")
        
        #Restore v1 using copy
        try:
            self.test_bucket.copy_key(new_key_name=obj_v1.key,src_bucket_name=self.test_bucket_name,src_key_name=keyname,src_version_id=obj_v1.version_id)
        except S3ResponseError as e:
            self.fail("Failed to restore key from previous version using copy got error: " + str(e.status))
            
        restored_obj = self.test_bucket.get_key(keyname)
        self.tester.check_md5(eTag=restored_obj.etag,data=v1data)
        self.print_key_info(keys=[restored_obj])
        
        #Put v3 again
        self.put_object(bucket=self.test_bucket, object_key=keyname,object_data=v3data)
        self.tester.check_md5(eTag=obj_v3.etag,data=v3data)
        self.print_key_info([self.test_bucket.get_key(keyname)])

        #Delete v2 explicitly
        self.test_bucket.delete_key(key_name=obj_v2.key,version_id=obj_v2.version_id)
        del_obj = self.test_bucket.get_key(keyname,version_id=obj_v2.version_id)
        if del_obj:
            raise S3ResponseError("Should have gotten 404 not-found error, but got: " + del_obj.key + " instead",404)

        #Show what's on top
        top_obj = self.test_bucket.get_key(keyname)
        self.print_key_info([top_obj])
        self.tester.check_md5(eTag=top_obj.etag,data=v3data)
        
        self.tester.info("Finished the versioning enabled test. Success!!")

    def clear_and_rebuild_bucket(self, bucket_name):
        self.tester.clear_bucket(bucket_name)
        return self.tester.create_bucket(bucket_name)

    def test_object_versionlisting(self):
        """
        Tests object version listing from a bucket
        """
        version_max = 3
        keyrange = 20
        self.tester.info("Testing listing versions in a bucket and pagination using " + str(keyrange) + " keys with " + str(version_max) + " versions per key")
        self.test_bucket = self.clear_and_rebuild_bucket(self.test_bucket_name)
        if not self.enable_versioning(self.test_bucket):
            self.fail("Could not enable versioning properly. Failing")
        
        key = "testkey-" + str(int(time.time()))
        keys = [ key + str(k) for k in range(0,keyrange)]        
        contents = [ self.test_object_data + "--v" + str(v) for v in range(0,version_max)]        

        try:
            for keyname in keys:
                #Put version_max versions of each key
                for v in range(0,version_max):
                    self.tester.info("Putting: " + keyname + " version " + str(v))
                    self.test_bucket.new_key(keyname).set_contents_from_string(contents[v])
        except S3ResponseError as e:
            self.fail("Failed putting object versions for test: " + str(e.status))
        listing = self.test_bucket.get_all_versions()
        self.tester.info("Bucket version listing is " + str(len(listing)) + " entries long")
        if keyrange * version_max >= 1000:
            if not len(listing) == 999:
                self.test_bucket.configure_versioning(False)
                self.tester.debug(str(listing))
                raise Exception("Bucket version listing did not limit the response to 999. Instead: " + str(len(listing)))
        else:
            if not len(listing) == keyrange * version_max:
                self.test_bucket.configure_versioning(False)
                self.tester.debug(str(listing))
                raise Exception("Bucket version listing did not equal the number uploaded. Instead: " + str(len(listing)))
        
        prev_obj = None
        for obj in listing:
            if isinstance(obj,Key):
                self.tester.info("Key: " + obj.name + " -- " + obj.version_id + "--" + obj.last_modified)                
                if prev_obj != None:
                    if self.compare_versions(prev_obj, obj) <= 0:
                        raise Exception("Version listing not sorted correctly, offending key: " + obj.name + " version: " + obj.version_id + " date: " + obj.last_modified)
                prev_obj = obj
            else:
                self.tester.info("Not a key, skipping: " + str(obj))
    
    def test_object_versioning_suspended(self):
        """Tests object versioning on a suspended bucket, a more complicated test than the Enabled test"""
        self.tester.info("Testing bucket Versioning-Suspended")
        self.test_bucket = self.clear_and_rebuild_bucket(self.test_bucket_name)
        #Create some keys
        keyname1 = "versionkey1-" + str(int(time.time()))
        keyname2 = "versionkey2-" + str(int(time.time()))
        keyname3 = "versionkey3-" + str(int(time.time()))
        keyname4 = "versionkey4-" + str(int(time.time()))
        keyname5 = "versionkey5-" + str(int(time.time()))
        v1data = self.test_object_data + "--version1"
        v2data = self.test_object_data + "--version2"
        v3data = self.test_object_data + "--version3"
        
        vstatus = self.test_bucket.get_versioning_status()
        if vstatus:
            self.fail("Versioning status should be null/Disabled but was: " + str(vstatus))
        else:
            self.tester.info("Bucket versioning is Disabled")
        
        self.put_object(bucket=self.test_bucket, object_key=keyname1, object_data=v1data)
        self.put_object(bucket=self.test_bucket, object_key=keyname2, object_data=v1data)
        self.put_object(bucket=self.test_bucket, object_key=keyname3, object_data=v1data)
        self.put_object(bucket=self.test_bucket, object_key=keyname4, object_data=v1data)
        self.put_object(bucket=self.test_bucket, object_key=keyname5, object_data=v1data)
                    
        key1 = self.test_bucket.get_key(keyname1)        
        key2 = self.test_bucket.get_key(keyname2)        
        key3 = self.test_bucket.get_key(keyname3)        
        key4 = self.test_bucket.get_key(keyname4)        
        key5 = self.test_bucket.get_key(keyname5)

        self.tester.info("Initial bucket state after object uploads without versioning:")
        self.print_key_info(keys=[key1,key2,key3,key4,key5])
        
        
        
        #Enable versioning
        self.test_bucket.configure_versioning(True)
        if self.test_bucket.get_versioning_status():
            self.tester.info("Versioning status correctly set to enabled")
        else:
            self.tester.info("Versionign status not enabled, should be.")            
        
        #Update a subset of the keys
        key1_etag2=self.put_object(bucket=self.test_bucket, object_key=keyname1,object_data=v2data)
        key2_etag2=self.put_object(bucket=self.test_bucket, object_key=keyname2,object_data=v2data)
        
        key3_etag2=self.put_object(bucket=self.test_bucket, object_key=keyname3,object_data=v2data)
        key3_etag3=self.put_object(bucket=self.test_bucket, object_key=keyname3,object_data=v3data)
        
        #Delete a key
        self.test_bucket.delete_key(keyname5)

        #Suspend versioning
        self.test_bucket.configure_versioning(False)
        
        #Get latest of each key
        key1=self.test_bucket.get_key(keyname1)
        key2=self.test_bucket.get_key(keyname2)
        key3=self.test_bucket.get_key(keyname3)
        key4=self.test_bucket.get_key(keyname4)
        key5=self.test_bucket.get_key(keyname5)
        
        #Delete a key
        
        #Add a key
        
        #Add same key again
        
        #Fetch each key
    
    def test_object_acl(self):
        """Tests object acl get/set and manipulation"""
        self.fail("Test not implemented")
        
        #TODO: test custom and canned acls that are both valid an invalid
        
    def test_object_torrent(self):
        """Tests object torrents"""
        self.fail("Feature not implemented yet")

    
    def clean_method(self):
        '''This is the teardown method'''
        #Delete the testing bucket if it is left-over
        self.tester.info('Deleting the buckets used for testing')
        for bucket in self.buckets_used:
            try:
                self.tester.info('Checking bucket ' + bucket + ' for possible cleaning/delete')
                if self.tester.s3.bucket_exists(bucket):
                    self.tester.info('Found bucket exists, cleaning it')
                    self.tester.clear_bucket(bucket)
                    self.buckets_used.remove(bucket)
                else:
                    self.tester.info('Bucket ' + bucket + ' not found, skipping')
            except:
                self.tester.info('Exception checking bucket ' + bucket)

        return
          
if __name__ == "__main__":
    
    testcase = ObjectTestSuite()
    ### Either use the list of tests passed from config/command line to determine what subset of tests to run
    list = testcase.args.tests or ['test_object_basic_ops', \
                                   #'test_object_byte_offset_read', \
                                   'test_object_large_objects', \
                                   'test_object_versionlisting', \
                                   'test_object_versioning_enabled', \
                                   'test_object_versioning_suspended']                                   
    ### Convert test suite methods to EutesterUnitTest objects
    unit_list = [ ]
    for test in list:
        unit_list.append( testcase.create_testunit_by_name(test) )
    ### Run the EutesterUnitTest objects

    result = testcase.run_test_case_list(unit_list,clean_on_exit=True)
    exit(result)