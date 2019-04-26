# Grute

Grute - aims to help with the heavy lifting of green screen, mainframe applications accessible via tn3270,  testing.  It is unlikely to work out of the box for you, and requires tuning for individual apps and enviroments.  Grute can do simple automation testing to do things taken for granted in other protocols (http).  Namely, enumeration, authentication testing, etc.  It started life as a branch of MFscreen which SoF wrote.  Variables and data should ideally live in the config xml file.  Grute makes use of rabbitmq to do some parrelised assessments.  ie, if you can open 10 connection from your system, you can run 10 instances of grute.


Sensitive operations can be described  inc/private_includes.py with dummy / default ones in inc/public_includes.py.  private includes are not checked in using .gitignore.

You will likely need to tune grute alot for individual enviroments, I've tried to use oop and repeatable actions where possible to automate the less interesting tasks.  


EG:
```
for i in {1..1000}
do
source ~/.virtualenvs/grute2/bin/activate
python Grute.py -t <target>:<port> -c True -u <user> -p <password> -mq localhost -ba True -v 0 -s 0.25 -e True
done
```


N.B - I like Mainframes, but am not a sysprog.  Terms may be incorrect, let me know and I'll fix.

### Getting Started

pip requirements are in the requirements file, create a virtualenv and install.  You may well want a MQ server as well depending on what your using.  Checkout the Docker & Rabbit MQ section.

```
mkvirtualenv /root/.virtualenvs/grute
source ~/.virtualenvs/grute/bin/activate
pip install -r requirements.txt
python Grute.py -h
```

### General Basics

Grutes application and cics parsing try to strip out the known knowns.  If you tell it about application and cics messages,
where and how it can see if the response is a known one, it will catagorise it as such.  It also writes the screenshots to disk
as html files so you can verify, or use in a report.

If you include diffrent types of test in the xml, it should create these queues for you, see check_cics_transactions &
check_application

```
        for name in ["app_unknown"]:
            self.channel = que_dec(self.channel, name)

        for dictionary in self.application_list_dict:
            self.channel = que_dec(self.channel, dictionary['type'])
```

I've basically lifted the rabbitmq's hello world examples.  There are probably all sorts of optimisation that could be made.

###### Connectivity

Hopefully easy to understand - tells grute how to connect, if you want to see the emulator (x or s 3270).  Of note is the enviroment switch, a boolean.  If you have an app accross diffrent regions or perhaps your assessing multiple enviroments (testing/pre-prod) then you can use this to switch between.  Be sure to update xml enviroment settings.  Currently it replaces a letter in a screen, but you can reprograme to your env.
```
 -h, --help            show this help message and exit
  -t TARGET, --target TARGET
                        target IP address or Hostname and port: TARGET[:PORT]
  -s SLEEP, --sleep SLEEP
                        Seconds to sleep between actions (increase on slower
                        systems). The default is 1 second.
  -v VISABLE, --visable VISABLE
                        uses x or s 3270. X is an X window system and is
                        visable Screen is generally used for scripting and
                        goes really fast by comparision - Bool
  -c CLOBBER, --clobber CLOBBER
                        remove target file on run, Bool
  -cfg CONFIG, --config CONFIG
                        configuration file for application dictionary setup
  -e ENV_SWITCH, --env_switch ENV_SWITCH
                        enters a character on the app screen to switch app
                        instance - Bool
  -d DEBUG, --debug DEBUG
                        More chatty - bool
```


###### Credentials

Credentials for testing, assume the vtam/initall login creds are the same, but you can supply differing ones.

```
-u USER, --user USER  supply a username name to connect with
  -p PASSWORD, --password PASSWORD
                        supply a password name to connect with
  -au APPUSER, --appuser APPUSER
                        supply a username name to connect with to the
                        appdefaults to the same value as --user
  -ap APPPASSWORD, --apppassword APPPASSWORD
                        supply a password name to connect with to the
                        appdefaults to the same value as --password
```

###### Helper functions

```
  -chg CHANGEPASS, --changepass CHANGEPASS
                        Change passwords helper, Bool
  -l LOGMEIN, --logmein LOGMEIN
                        just starts an emulator and logs you in, bool
  -ct CEMT_TRANS, --cemt_trans CEMT_TRANS
                        cemt transaction scraping , Bool
```

Some helper functions.
- Changepass resets the password to one of your choosing (supplied in xml), from a default value.  Useful if passwords are reset daily for testing
- logmein - sets the emulator to visable, and logs you into the app so you dont need to type creds repetivitly etc.
- cemt_trans - scrapes cics transactions from cemt - assuming you can get to it, which allows more direct testing



## Docker & rabbit MQ

Grute uses rabbit mq to store and process transactions, such as app codes & cics regions.  You can setup a quick docker
with the follow, to create a container called jessica:

```
docker volume create jessica_log
docker volume create jessica_data


docker run -d -v "jessica_log:/var/log/rabbitmq"  -v "jessica_data:/var/lib/rabbitmq"  --hostname jessica \n
--name jessica  --publish="4369:4369"  --publish="5671:5671"  --publish="5672:5672"  --publish="15671:15671" \n
--publish="15672:15672"  --publish="25672:25672" rabbitmq:3-management
```

Check logs for correct boot up, with:

```
docker logs jessica
```

Watch for:
```
 node           : rabbit@jessica
 home dir       : /var/lib/rabbitmq
 config file(s) : /etc/rabbitmq/rabbitmq.conf

 [...]

2019-03-21 12:44:57.818 [info] <0.548.0> Management plugin: HTTP (non-TLS) listener started on port 15672
2019-03-21 12:44:57.818 [info] <0.654.0> Statistics database started.
2019-03-21 12:44:57.996 [info] <0.8.0> Server startup complete; 3 plugins started.
```

Hopefully, you should then get a management interface on:

- http://localhost:15672/#/queues

The default creds are guest/guest

Grute uses persistant queues and messages, so it *should* be restart safe.  YMMV




## Authors

* **Adam H - Incendiary** - *Initial work* - [incendiary](https://github.com/incendiary)

## Acknowledgments

* Based off lots of work by: Soldier of Fortran (@mainframed767) [github](https://github.com/mainframed) [Twitter](https://twitter.com/mainframed767) - Thanks :-)

