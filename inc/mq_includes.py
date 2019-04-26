import pika
import time
import random
import string
from public_includes import screen
import sys

debug_value = False

# Buggy transactions that hang or crash CICS
cicsexceptions = ['AORQ', 'CEJR','CJMJ','CPCT','CKTI','CPSS','CPIR','CRSY','CSFU','CRTP','CSZI','CXCU','CXRE','CMPX','CKAM','CEX2']

def returnmq(args):
    ##
    #   Returns all the results of a specific que
    ##
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=args.mq))
    channel = connection.channel()
    channel.queue_declare(queue=args.que.lower(), durable=True)
    print(' [*] Waiting for messages for %s. To exit press CTRL+C' % args.mq)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(callback, queue=args.que)
    channel.start_consuming()


def callback(ch, method, properties, body):
    ##
    #   Callback used to pull messages from queue
    ##

    time.sleep(body.count(b'.'))
    ch.basic_ack(delivery_tag=method.delivery_tag)


def populate_mq(args, prepend=None, apend=None):
    ##
    #   Used to populate our queues with generated strings
    ##
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=args.mq))
    channel = connection.channel()

    if args.populate_users:
        char_set = string.ascii_lowercase + string.digits
        routing_key = create_mq_routing_key("users", prepend, apend)

    elif args.populate_cics:
        char_set = string.ascii_lowercase
        routing_key = create_mq_routing_key("cics", prepend, apend)

    elif args.populate_apps:
        char_set = string.ascii_lowercase + string.digits
        routing_key = create_mq_routing_key("app", prepend, apend)
    else:
        print "unknown queue"
        sys.exit()

    # channel = que_dec(channel, routing_key)  dont think we need reasignment
    que_dec(channel, routing_key, args.destructive)

    for positionone in char_set:
        for positiontwo in char_set:
            for positionthree in char_set:
                if args.populate_apps:
                    resulting_string = positionone + positiontwo + positionthree
                    mq_basic_publish(channel, routing_key, resulting_string)

                elif args.populate_cics or args.populate_users:
                    for positionfour in char_set:
                        resulting_string = positionone + positiontwo + positionthree + positionfour
                        if (args.populate_cics and resulting_string not in cicsexceptions) or args.populate_users:
                            mq_basic_publish(channel, routing_key, resulting_string)


    channel.close()
    connection.close()


def mq_basic_publish(channel, routing_key, body):
    ##
    #   Publishes our message to a queue
    ##
    #screen("MQ publish key %s - body: %s" % (routing_key, body), type='debug', level=2)

    channel.basic_publish(exchange='', routing_key=routing_key.lower(), body=body,
                          properties=pika.BasicProperties(delivery_mode=2))


def create_mq_routing_key(basename, prepend=None, apend=None):
    ##
    #  Formats our routing key
    ##
    if prepend is not None:
        routing_key = prepend + basename
    else:
        routing_key = basename

    if apend is not None:
        routing_key += apend

    return routing_key


def que_dec(channel, name, destructive=False):
    ##
    #   Creates a queue, destroys if instructed.
    ##
    print "[*] Creating: %s" % name

    if destructive:
        channel.queue_delete(queue=name)

    channel.queue_declare(queue=name.lower(), durable=True)
    return channel


def pop_queue(args, queue):
    ##
    #   Pops a message from a queue
    ##
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=args.mq))
    channel = connection.channel()

    try:
        queue_state = channel.queue_declare(queue.lower(), durable=True, passive=True)
        queue_empty = queue_state.method.message_count == 0

        #print "[P] Processing %s" % queue

        if not queue_empty:
            method, properties, body = channel.basic_get(queue, no_ack=True)
            callback(channel, method, properties, body)
            if args.debug:
                print "[p] processing %s" % body
            return body
        else:
            return None

    except:
        return None

def return_queue_contents(queue, args):

    list_of_responses = []
    response = ""
    while response is not None:
        response = pop_queue(args, queue)
        list_of_responses.append(response)

    return list_of_responses


def populate_mq_for_excel(user_list_dict, env_list_dict, app_list_dict, args):
    ##
    #   Used to populate our queues with generated strings for testing
    ##
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=args.mq))
    channel = connection.channel()

    char_set = string.ascii_lowercase + string.digits

    ques = []

    for user_dict in user_list_dict:
        for env_dictionary in env_list_dict:
            prepend_string = "%s_%s_" % (user_dict['user'], env_dictionary['name'])

            for app_dict in app_list_dict:
                que_name = prepend_string + app_dict['type']
                que_dec(channel, que_name, destructive=True)
                que_dec(channel, prepend_string + "app", destructive=True)
                ques.append(que_name)

    for positionone in char_set:
        for positiontwo in char_set:
            for positionthree in char_set:

                resulting_string = positionone + positiontwo + positionthree
                routing_key = random.choice(ques)

                mq_basic_publish(channel, routing_key, resulting_string)

                routing_key = random.choice(ques)

                mq_basic_publish(channel, routing_key, resulting_string)

                routing_key = random.choice(ques)

                mq_basic_publish(channel, routing_key, resulting_string)

                routing_key = random.choice(ques)

                mq_basic_publish(channel, routing_key, resulting_string)
