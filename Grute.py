#!/usr/bin/python

##################################################################
#                                                                #
# Requirements: Python, x3270                                    #
# Orig Created by: Soldier of Fortran (@mainframed767)           #
#                                                                #
# Copyright GPL 2012                                             #
##################################################################

from py3270 import EmulatorBase
import time  # needed for sleep
import sys
import os
import platform  # needed for OS check
import string
import pika
from collections import defaultdict
from pprint import pprint
import itertools


#Private includes include the potentialyl sensitive includes, for exmaple the default password structure for an
# enviroemt
try:
    from inc.private_includes import return_password_reset_string

except:
    from inc.public_includes import return_password_reset_string

from inc.public_includes import do_setup, read_xml, make_excel_workbook, process_mq_results_into_excel, \
    save_excel_workbook, set_creds, screen, set_debug
from inc.mq_includes import returnmq, populate_mq, pop_queue, create_mq_routing_key, que_dec, \
    populate_mq_for_excel, mq_basic_publish, return_queue_contents

# Buggy transactions that hang or crash CICS
cicsexceptions = ['AORQ', 'CEJR','CJMJ','CPCT','CKTI','CPSS','CPIR','CRSY','CSFU','CRTP','CSZI','CXCU','CXRE','CMPX','CKAM','CEX2']
debug_value = False


class MainFrame:

    def __init__(self, target, sleep, clobber, credentials,  args):
        """
        :param target: Target in the form of host:port
        :param sleep: Sleep to use in default user supplied sleep timings
        :param clobber: Clobers existing file - not used much any more
        :param credentials: Credentials dictonary to login to the mf
        :param args: args object which includes the user supplied args
        """
        self.target = target
        self.host = target.split(':')[0]
        self.port = target.split(':')[1]
        self.sleep = sleep
        self.credentials = credentials
        self.nice_file_name = "%s_%s" % (self.host, self.port)
        self.nice_file_name_html = self.nice_file_name + ".html"
        self.clobber = clobber

        self.args = args

        self.transaction_codes = []
        self.disclosed_accounts = []
        self.disclosed_priv_accounts = []

        self.region_login_position = None
        self.channel = None
        self.application_list_dict = None
        self.cics_response = None
        self.cics_region = None
        self.cics_continue = None
        self.cics_list_dict = None
        self.cics_region = None
        self.app_code = None
        self.application_response = None
        self.app_continue = None
        self.check_username_continue = None
        self.username_to_check = None
        self.password_reset_accounts = None
        self.username_field_location_dict = None
        self.username_responses_list_dict = None
        self.username_response = None
        self.environment = None
        self.bulk_app_mode = False
        self.application_response_folder = None
        self.path_to_folder = None
        self.mq_queue = None
        self.debug = args.debug
        self.overtype = False

        # Removes existing file if requested
        if self.clobber:
            if os.path.exists(self.nice_file_name_html):
                os.remove(self.nice_file_name_html)
            else:
                screen('Clobber requested but file doesnt exist', type='info')

        if platform.system() == 'Darwin':  # 'Darwin'
            class Emulator(EmulatorBase):
                x3270_executable = 'MAC_Binaries/x3270'
                s3270_executable = 'MAC_Binaries/s3270'

        elif platform.system() == 'Linux':
            class Emulator(EmulatorBase):
                x3270_executable = 'lin_Binaries/x3270'
                s3270_executable = 'lin_Binaries/s3270'

        else:
            screen('[!] Your Platform:' + platform.system() + 'is not supported at this time. ', type='err')
            sys.exit()

        self.em = Emulator(visible=self.args.visable)

    def connect_to_zos(self):
        # Connects to target
        screen('Connecting to: ' + self.target, type='info')

        trying = False
        try:
            self.em.connect(self.target)
            trying = True
        except:
            trying = False
        return trying

    def set_bulk_app_mode_true(self, state=True):
        ##
        # Sets the bulk app mode testing
        ##
        self.bulk_app_mode = state

    def set_environment(self, enviroment):
        ##
        # Sets the enviroment dict from xml
        ##

        self.environment = enviroment

    def get_enviroment(self):
        return self.environment

    def set_overtype(self, overtype):
        ##
        # Sets the overtype dict from xml
        ##
        self.overtype = overtype

    def print_countdown(self):
        # prints a countdown to an action

        screen('Sleeping for : %s' % str(self.sleep), type='info')
        snooze = self.sleep - 1
        while snooze > 0:
            time.sleep(1)
            screen(snooze, type='info')
            snooze -= 1

    def terminate(self):
        # Kills things indiscriminately, Hasta la vista, baby
        self.em.terminate()

    def wait_for_field(self):
        self.em.wait_for_field()

    def wait_for_field_and_screenshot(self):
        """
        Helper to wrap these two together
        :return:
        """
        self.em.wait_for_field()
        self.save_screen_normal()

    def vtam_login(self):
        """
        Logs you into the MF, uses the credential dict supplied at init.
        :return:
        """
        self.em.send_string(self.credentials['vtamcredentials']['user'])
        self.send_tab_x_times(4)

        self.em.send_string(self.credentials['vtamcredentials']['password'])
        self.do_sleep()
        self.em.wait_for_field()
        self.em.send_enter()

    def set_region(self, region_login_position_list_dict):
        """
        Sets our region info, expects a list of dicts, but sets just the first dicts
        :param region_login_position_list_dict:
        """
        self.region_login_position = region_login_position_list_dict[0]

    def login_to_region(self):
        """
        Moves the cursor to a defined region for login, used to select from a menu
        """
        self.em.send_enter()
        self.em.move_to(int(self.region_login_position['ypos']), int(self.region_login_position['xpos']))
        self.em.send_enter()

    def do_sleep(self):
        """
        You told me to sleep.
        """
        time.sleep(self.sleep)

    def login_to_app(self):
        """
        Logs us into our app for testing
        """
        self.em.send_string(self.credentials['appcredentials']['user'])
        self.send_tab_x_times(3)
        self.em.send_string(self.credentials['appcredentials']['password'])
        if self.environment:
            self.em.send_string(self.environment['value'], int(self.environment['ypos']),
                                int(self.environment['xpos']))

        self.wait_for_field()
        self.em.send_enter()
        if self.args.overtype:

            #  Below assumes we set these overtypes on the same pane

            self.wait_for_field()
            for d in self.overtype:
                self.em.send_string(self.d['value'], int(self.d['ypos']), int(self.d['xpos']))
                self.do_sleep()  # maybe better than wait for field?

    def save_screen_normal(self):
        ##
        #  Appends to html file in cwd
        ##
        self.make_path_to_file(self.nice_file_name_html)
        self.save_screen_specific(self.nice_file_name_html)

    def save_screen_specific(self, fn):
        ##
        # Saves the screen to a specific location
        ##
        self.make_path_to_file(fn)
        screen('Saving screen to: ' + fn, type='info')

        command = 'printtext(html,' + fn + ')'
        self.em.exec_command(command)

    def make_path_to_file(self, fn):
        ##
        # Creates a path to file before creating.
        ##
        filename = os.path.basename(fn)
        path = fn.split(filename)[0]

        if len(path) > 0:
            #  0 len path is CWD.
            if not os.path.exists(path):
                try:
                    os.makedirs(path)
                except OSError, e:
                    if e.errno != os.errno.EEXIST:
                        raise
                    pass

    def send_tab_x_times(self, x):
        ##
        # Sends tab to the emulator X times
        ##
        for i in range(0, x):
            self.em.exec_command('Tab()')

    # Password Stuff

    def add_password_reset_info(self, info):
        ##
        #  Addds password reset account information list of dicts
        ##
        self.password_reset_accounts = info

    def change_passwords(self):
        ##
        #  process to reset the passwords from a daily reset
        ##
        daily_password_reset = return_password_reset_string()

        self.connect_to_zos()
        for account in self.password_reset_accounts:
            screen('connected: ', type='info')

            self.em.wait_for_field()
            screen('Changing password for: %s to: %s' % (account['user'], account['password']), type='info')

            self.em.send_string(account['user'])
            self.send_tab_x_times(4)
            self.em.send_string(daily_password_reset)
            time.sleep(self.sleep)
            self.send_tab_x_times(8)
            self.em.send_string(account['password'], ypos=18, xpos=17)
            time.sleep(self.sleep)
            self.em.send_enter()
            self.em.send_string(account['password'], ypos=18, xpos=17)
            time.sleep(self.sleep)
            self.em.send_enter()
            time.sleep(self.sleep)
            self.em.reconnect()

    def make_and_set_folder_path(self):
        self.path_to_folder = None
        self.application_response_folder = None

        if self.environment is not None:
            self.path_to_folder = "app/%s/%s/%s/%s/%s" % (self.credentials['appcredentials']['user'],
                                                          self.environment['name'],
                                                          self.application_response, self.app_code[0],
                                                          self.app_code[1])
        else:
            self.path_to_folder = "app/%s/%s/%s/%s" % (self.credentials['appcredentials']['user'],
                                                       self.application_response, self.app_code[0],
                                                       self.app_code[1])

    # CICS stuff

    def get_to_cics(self, cics_list_dict):
        self.cics_list_dict = cics_list_dict
        self.em.send_string('cic')
        self.em.send_enter()
        time.sleep(self.sleep)
        self.em.send_string('CESN', 1, 2)
        self.em.send_enter()
        time.sleep(self.sleep)
        self.em.send_string(self.credentials['appcredentials']['user'], 10, 26)
        self.em.send_string(self.credentials['appcredentials']['password'], 11, 26,)
        self.em.send_enter()

    def assess_cics_screen(self):
        if self.cics_region not in cicsexceptions:
            self.em.send_string(self.cics_region)
            self.em.send_enter()
            time.sleep(5)

            #  list dict like:
            #  [{'xpos': '2', 'type': 'cics_error', 'string': 'DFHAC2001', 'ypos': '23'},
            #  {'xpos': '2', 'type': 'cics_auth', 'string': 'DFHAC2033', 'ypos': '23'}]

            for dictionary in self.cics_list_dict:
                # check to see if the string /erroc code is found
                if self.em.string_found(int(dictionary['ypos']), int(dictionary['xpos']), dictionary['string']):
                    screen("checking: %s != %s" % (self.cics_region.lower(),
                                                   self.em.string_get(int(dictionary['eypos']),
                                                                      int(dictionary['expos']),
                                                                      len(self.cics_region)).lower()), type='info')

                    # Need to check here ot see if cics region is returned
                    if not self.cics_region.lower() == self.em.string_get(int(dictionary['eypos']),
                                                                          int(dictionary['expos']),
                                                                          len(self.cics_region)).lower():
                        # Auth and unknown return the cics region at this position in an error message.
                        # if its not here, it implies something is wrong, see screens which get stuck with a region
                        # restart
                        self.cics_response = "cics_unknown_wierd"
                        screen('Found unknown screen: %s' % self.cics_region, 'err')

                        # if the cics region isnt here we are either on an unknown or weird page
                        # break out of the if
                        break
                    else:
                        self.cics_response = dictionary['type']
                    break

                else:
                    # Error code not know, this is an unknwon page at this point
                    self.cics_response = "cics_unknown"
                    screen('Found unknown screen: %s' % self.cics_region, 'err')

            self.save_screen_specific("cics/%s/%s/%s/%s.html" % (self.cics_response, self.cics_region[0],
                                                                 self.cics_region[1], self.cics_region))

    def check_cics_transactions(self):
        self.cics_continue = True
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.args.mq))
        self.channel = connection.channel()
        self.channel.basic_qos(prefetch_count=1)

        for name in ["cics_unknown", "cics_unknown_weird"]:
            self.channel = que_dec(self.channel, name)

        for dictionary in self.cics_list_dict:
            self.channel = que_dec(self.channel, dictionary['type'])

        while self.cics_continue:
            # Get a message and break out
            for method_frame, properties, body in self.channel.consume('cics'):
                # Display the message parts
                self.cics_region = body
                self.assess_cics_screen()

                # Acknowledge the message
                self.channel.basic_ack(method_frame.delivery_tag)

                mq_basic_publish(self.channel, routing_key=self.cics_response, body=self.cics_region)

                if "unknown" in self.cics_response:
                    # Got an unknown response, don't wish to continue, screen in unknown state.

                    screen('Interesting transaction at %s' % self.cics_region, type='err')
                    screen('Got an unknown response, dont wish to continue, screen in unknown state', type='err')
                    self.do_sleep()

                    self.cics_continue = False
                    self.terminate()
                    break

                # Escape out of the loop after 1 messages
                if method_frame.delivery_tag == 1:
                    break

            # Cancel the consumer and return any pending messages
            self.channel.cancel()
            # print 'Requeued %i messages' % requeued_messages

        # Close the self.channel and the connection
        self.channel.close()
        connection.close()

    # App stuff
    def look_for_app_code(self):
        # Should only be here if we have an app code match from a generator
        for dict in self.application_list_dict:

            screen("Looking for %s at x:%s y:%s" %(dict['string'], dict['xpos'], dict['ypos']), type='debug', level=1)
            screen("found %s" % self.em.string_get(int(dict['ypos']), int(dict['xpos']), len(dict['string'])),
                   type='debug', level=1)

            if self.em.string_found(int(dict['ypos']), int(dict['xpos']), dict['string']):

                self.application_response = dict['type']

                if self.bulk_app_mode:
                    prepend_string = "%s_%s_" % (self.credentials['appcredentials']['user'], self.environment['name'])
                    self.mq_queue = prepend_string + dict['type']

                else:
                    self.mq_queue = dict['type']

                return

    def assess_app_screen(self):

        self.em.send_clear()
        self.em.send_string(self.app_code)
        screen("Sent App Code", type="debug")
        self.em.send_enter()
        # time.sleep(0.3)  # Needed?
        # self.em.wait_for_field()
        # Above causes issues when fields don't reactivate

        try:
            self.em.wait_for_field()
        except:
            self.do_sleep()

        # resetting these on each assesment to avoid overun.
        self.application_response = None
        self.mq_queue = None

        # dict should be something like:
        # [{'xpos': '28', 'string': 'ERROR', 'ypos': '5'},

        if self.app_code == "sfa" or self.app_code == "sys":
            self.application_response = "app_unknown"
            self.mq_queue = "app_unknown"
            if self.bulk_app_mode:
                prepend_string = "%s_%s_" % (self.credentials['appcredentials']['user'], self.environment['name'])

                self.mq_queue = prepend_string + "app_unknown"

        if not any(d['string'].lower() == self.em.string_get(int(d['ypos']), int(d['xpos']), len(d['string'])).lower()
                  for d in self.application_list_dict):

            # Above generator returns true if any of the identified responses are present. replicate for cics
            self.application_response = "app_unknown"
            self.mq_queue = "app_unknown"

            if self.bulk_app_mode:
                prepend_string = "%s_%s_" % (self.credentials['appcredentials']['user'], self.environment['name'])

                self.mq_queue = prepend_string + "app_unknown"

        if self.check_screen_for_string("Retry later if signon is rejected") and self.app_code != "sfa" and self.app_code != "sys":
            # At cics screen restart
            screen("At login screen stuck, restarting", type="err")
            self.terminate()
            sys.exit()

        if self.check_screen_for_string("DFHAC2001") and self.app_code != "sfa" and self.app_code != "sys":
            # At cics screen restart
            screen("At login screen stuck, restarting", type="err")
            self.terminate()
            sys.exit()

        else:
            self.look_for_app_code()

        self.make_and_set_folder_path()

        self.save_screen_specific("%s/%s.html" % (self.path_to_folder, self.app_code))

    def check_application(self, application_list_dict):
        self.application_list_dict = application_list_dict

        self.app_continue = True
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.args.mq))
        self.channel = connection.channel()
        self.channel.basic_qos(prefetch_count=1)

        ##
        # Feel singular function should be the same as list, but a list of 1 element, review.
        ##

        if self.bulk_app_mode:
            prepend_string = "%s_%s_" % (self.credentials['appcredentials']['user'], self.environment['name'])

            for dictionary in self.application_list_dict:
                self.channel = que_dec(self.channel, prepend_string + dictionary['type'])

            que_to_consume = prepend_string + 'app'

        else:

            for dictionary in self.application_list_dict:
                self.channel = que_dec(self.channel, dictionary['type'])

            que_to_consume = 'app'

        while self.app_continue:
            # Get a message and break out

            screen("Consuming: %s" % que_to_consume, type="info")

            for method_frame, properties, body in self.channel.consume(que_to_consume.lower()):

                # Display the message parts
                self.app_code = body

                screen("Assessing %s" % self.app_code, type="debug")

                if self.app_code == "sfa" or self.app_code == "sys":
                    self.channel.basic_ack(method_frame.delivery_tag)
                else:
                    self.assess_app_screen()

                screen("Assessing complete", type="debug")

                # Acknowledge the message
                self.channel.basic_ack(method_frame.delivery_tag)

                screen("response: %s \tcode:%s" % (self.application_response, self.app_code), type="debug", level=1)

                screen("MQ: %s" % (self.mq_queue), type="debug", level=1)

                mq_basic_publish(self.channel, routing_key=self.mq_queue, body=self.app_code,)

                if "unknown" in self.application_response:
                    # Got an unknown response, don't wish to continue, screen in unknown state.

                    print '[E] Unknown app transaction at %s' % self.mq_queue
                    print "[E] Got an unknown response, don't wish to continue, screen in unknown state"

                    time.sleep(self.sleep)

                    self.app_continue = False
                    self.terminate()
                    break

                if self.environment['default'] is 'False' and "auth" in self.application_response:
                    ##
                    #   Environmental difference means we have to restart if in the secondary env and hit an auth error
                    ##
                    print '[E] Got Auth in secondary enviroment, restarting'
                    time.sleep(self.sleep)

                    self.app_continue = False
                    self.terminate()
                    break

                # Escape out of the loop after 1 messages
                if method_frame.delivery_tag == 1:
                    break

            # Cancel the consumer and return any pending messages
            self.channel.cancel()
            # print 'Requeued %i messages' % requeued_messages

        # Close the self.channel and the connection
        self.channel.close()
        connection.close()

    # login enum check

    def check_login(self):
        self.check_username_continue = True
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.args.mq))
        self.channel = connection.channel()
        self.channel.basic_qos(prefetch_count=1)

        for name in ["user_valid", "user_invalid", "user_unknown"]:
            self.channel = que_dec(self.channel, name)

        while self.check_username_continue:
            # Get a message and break out

            for method_frame, properties, body in self.channel.consume('users'):

                # Display the message parts
                self.username_to_check = body
                self.assess_login_screen()

                # Acknowledge the message
                self.channel.basic_ack(method_frame.delivery_tag)

                print "[*] user %s is  %s" % (self.username_to_check, self.username_response)

                self.channel.basic_publish(exchange='', routing_key=self.username_response, body=self.username_to_check,
                                           properties=pika.BasicProperties(delivery_mode=2))

                if "unknown" in self.username_response:
                    # Got an unknown response, don't wish to continue, screen in unknown state.

                    print  'Unknown response with %s' % self.username_to_check
                    print "[X] Got an unknown response, don't wish to continue, screen in unknown state"

                    self.check_username_continue = False
                    self.terminate()
                    break

                # Escape out of the loop after 1 messages
                if method_frame.delivery_tag == 1:
                    break

            # Cancel the consumer and return any pending messages
            self.channel.cancel()

        # Close the self.channel and the connection
        self.channel.close()
        connection.close()

    def add_username_field_location(self, list):
        self.username_field_location_dict = list[0]

    def add_username_responses(self, list):
        self.username_responses_list_dict = list

    def assess_login_screen(self):
        self.em.wait_for_field()
        self.em.send_string(self.username_to_check,
                            ypos=int(self.username_field_location_dict['ypos']),
                            xpos=int(self.username_field_location_dict['xpos']))

        self.em.send_enter()

        if not any(d['string'].lower() == self.em.string_get(int(d['ypos']), int(d['xpos']), len(d['string'])).lower()
                   for d in self.username_responses_list_dict):
            # Above generator returns true if any of the identified responses are present. replicte for cics
            self.username_response = "user_unknown"

        else:
            self.look_for_login_code()
        self.save_screen_specific("login/%s/%s.html" % (self.username_response,  self.username_to_check))

    def look_for_login_code(self):
        # Should only be here if we have an login code match from a generator
        for d in self.username_responses_list_dict:
            if d['string'].lower() == self.em.string_get(int(d['ypos']), int(d['xpos']), len(d['string'])).lower():
                self.username_response = d['type']
                return

    def check_screen_for_string(self, string):

        data_list = self.em.screen_get()

        if not any(string.lower() in data_line.lower() for data_line in data_list):
            return False
        else:
            return True

    def count_occurances_in_screen(self, string):
        ##
        # Counts the number of occurances of a string on a screen
        ##
        i = 0
        data_list = self.em.screen_get()

        if self.check_screen_for_string(string):
            return sum(str(string) in line for line in data_list)
        else:
            return False

    def find_cemt_transactions_on_screen(self):
        char = ['Tra', '(', ')']
        data_list = self.em.screen_get()
        for data_line in data_list:
            for split_elements in data_line.split():
                if "tra(" in split_elements.lower():
                    region = split_elements.translate(None, ''.join(char))
                    self.transaction_codes.append(region)

    def get_cemt_transactions(self):
        self.em.send_clear()
        self.em.send_string('cemt')
        self.em.send_enter()
        self.em.send_string('i trans')
        self.em.send_enter()
        screen("Should be in CEMT trans.  Starting Scrape", type="info")

        screen("Identifying Transaction Codes:", type="info", level=1)

        self.find_cemt_transactions_on_screen()

        self.em.send_pf8()

        while self.count_occurances_in_screen('+') >= 2:
            self.find_cemt_transactions_on_screen()

            time.sleep(0.05)
            self.em.send_pf8()

        else:
            if len(self.transaction_codes) > 0:
                # Should be on final pane.
                self.find_cemt_transactions_on_screen()

                chunks = [self.transaction_codes[x:x+5] for x in xrange(0, len(self.transaction_codes), 5)]
                for chunk in chunks:
                    screen(str(chunk), type="info", level=2)

            else:
                screen("Unexpected Screen", type="err")
                sys.exit()


def main():
    # The below is a bit messy, but proceduarlly shows how things can be done.  Will tidy next opportunity i get
    # to test breaking changes.

    args = do_setup()
    app_list_dict = read_xml(args.config, 'application')
    env_list_dict = read_xml(args.config, 'environment')
    user_list_dict = read_xml(args.config, 'account')
    overtype_list_dict = read_xml(args.config, 'overtype')
    region_login_position_list_dict = read_xml(args.config, 'region_login_position')

    if args.debug:
        set_debug(True)
    else:
        set_debug(False)

    if args.populate_cics or args.populate_apps or args.populate_users:
        populate_mq(args)
        sys.exit(0)

    if args.bulk_auth_create:
        args.populate_apps = True

        for user_dict in user_list_dict:
            for env_dictionary in env_list_dict:
                prepend_string = "%s_%s_" % (user_dict['user'], env_dictionary['name'])
                populate_mq(args, prepend_string)
        sys.exit(0)

    if args.excel:
        ##
        #   Creates Spreadsheets, everyone loves spreadsheets
        ##

        if args.gen_excel_testing:
            populate_mq_for_excel(user_list_dict, env_list_dict, app_list_dict, args)

        wb = make_excel_workbook(user_list_dict, env_list_dict)

        for user_dict in user_list_dict:
            for env_dictionary in env_list_dict:
                prepend_string = "%s_%s_" % (user_dict['user'], env_dictionary['name'])
                print prepend_string

                for app_dict in app_list_dict:
                    ##
                    # So this should generate our queuenames.  Create a list of all transactions in that queue
                    ##
                    que_name = prepend_string + app_dict['type']
                    application_code_list = return_queue_contents(que_name, args)
                    for application_code in application_code_list:
                        if application_code is not None:
                            wb = process_mq_results_into_excel(wb, user_dict['user'],
                                                               env_dictionary['name'], app_dict['type'],
                                                               application_code)

        save_excel_workbook(wb)
        sys.exit()

    if args.manual_inport:
        with open(args.file_input) as f:
            codelist = f.read().splitlines()

        screen("[L]ength is %s" % len(codelist), type="info")

        connection = pika.BlockingConnection(pika.ConnectionParameters(host=args.mq))
        channel = connection.channel()
        que_dec(channel, args.que, args.destructive)

        for code in codelist:
            screen("[P]ushing: %s" % code, type="debug")

            mq_basic_publish(channel, args.que, code)
        sys.exit()

    if args.manual_export:
        application_code_list = return_queue_contents(args.que, args)

        f = open(args.file_output, 'w')
        print application_code_list[-1]

        if application_code_list[-1] is None:
            application_code_list.pop()

        print application_code_list

        for ele in application_code_list:
            f.write(ele + '\n')

        f.close()
        sys.exit()

    credentials = set_creds(args)

    target = MainFrame(args.target, args.sleep, args.clobber, credentials, args)

    if args.changepass:
        target.add_password_reset_info(read_xml(args.config, 'account'))
        target.change_passwords()
        time.sleep(args.sleep)
        sys.exit()

    if args.logmein:
        if target.connect_to_zos():
            screen("Connected", type="info")
            target.wait_for_field_and_screenshot()
            target.vtam_login()
            target.save_screen_normal()
            target.set_region(region_login_position_list_dict)
            target.login_to_region()
            time.sleep(args.sleep)
            target.login_to_app()
            time.sleep(args.sleep)
            while True:
                time.sleep(1)

    if args.check_cics:
        cics_list_dict = read_xml(args.config, 'cics')

        if target.connect_to_zos():
            screen("Connected", type="info")
            target.wait_for_field_and_screenshot()
            target.vtam_login()
            target.save_screen_normal()
            target.set_region(region_login_position_list_dict)
            target.login_to_region()
            target.login_to_app()
            target.save_screen_normal()
            target.get_to_cics(cics_list_dict)
            screen("Should be in CICS", type="info")
            time.sleep(1)
            target.check_cics_transactions()
            target.terminate()

    if args.check_user:

        if target.connect_to_zos():

            target.add_username_field_location(read_xml(args.config, 'username_login_field_location'))
            target.add_username_responses(read_xml(args.config, 'username_response'))

            screen("Connected", type="info")
            target.check_login()
            target.terminate()

    if args.bulk_auth:
        target.set_bulk_app_mode_true()

    if args.env_switch:
        for environment in env_list_dict:
            if environment["default"].lower() == "false".lower():
                target.set_environment(environment)
                break
    else:
        for environment in env_list_dict:

            if environment["default"].lower() == "true".lower():
                target.set_environment(environment)
                break

    screen(str(target.get_enviroment()), type="info")

    if args.check_app or args.bulk_auth:
        if target.connect_to_zos():
            screen("[Enviroment] %s" % target.environment, type="debug")
            screen("Connected", type="info")
            if args.overtype:
                target.set_overtype(overtype_list_dict)
            target.wait_for_field_and_screenshot()
            target.vtam_login()
            target.save_screen_normal()
            target.set_region(region_login_position_list_dict)
            target.login_to_region()
            time.sleep(args.sleep)
            target.login_to_app()
            time.sleep(args.sleep)
            target.save_screen_normal()
            time.sleep(args.sleep)
            screen("Should be in App", type="info")
            target.check_application(app_list_dict)
            target.terminate()

    if args.cemt_trans:
        cics_list_dict = read_xml(args.config, 'cics')
        if target.connect_to_zos():
            screen("Connected", type="info")
            target.wait_for_field_and_screenshot()
            target.vtam_login()
            target.save_screen_normal()
            target.set_region(region_login_position_list_dict)
            target.login_to_region()
            target.login_to_app()
            target.save_screen_normal()
            target.get_to_cics(cics_list_dict)
            screen("Should be in CICS", type="info")
            target.get_cemt_transactions()


if __name__ == "__main__":
    main()
