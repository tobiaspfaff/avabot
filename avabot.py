import md5
import os
import pysftp
import requests
import shutil
import time
import uuid
import websocket

from slackclient import SlackClient

# avabot's ID as an environment variable
BOT_ID = os.environ.get("BOT_ID")
BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
FTP_URL = os.environ.get('FTP_URL')
FTP_USER = os.environ.get('FTP_USER')
FTP_PASS = os.environ.get('FTP_PASS')
FTP_DIR = os.environ.get('FTP_DIR')
MAGIC_WORD = os.environ.get('MAGIC_WORD')
MAGIC_DELETE = os.environ.get('MAGIC_DELETE')

FILELIST_TXT = 'uploadedFiles.txt'
FILELIST_JS = 'imagelist.js'


# constants
AT_BOT = "<@" + BOT_ID + ">"

# instantiate Slack & Twilio clients
slack_client = SlackClient(BOT_TOKEN)


class Message(object):
    def __init__(self, type, channel, text):
        self.type = type
        self.channel = channel
        self.text = text

        if text and MAGIC_DELETE in text.lower() and MAGIC_WORD in text.lower():
            openBracket = text.find("[")
            closeBracket = text.find("]")
            if openBracket < 0 or closeBracket < 0:
                self.response =\
                    "Which {}? Tell me using [brackets]".format(MAGIC_WORD)
            else:
                filename = text[openBracket+1:closeBracket]
                try:
                    self.response = "I'll miss that " + MAGIC_WORD
                    delete_image(filename)
                except IOError:
                    self.response = "I could not find any such " + MAGIC_WORD

        # Uncomment for manual mode
        # if text:
        #     print "Respond to ", text
        #     self.response = raw_input()
        # else:
        #     self.response = None

class File(Message):
    def __init__(self, file_id):
        Message.__init__(self, 'file', None, None)
        self.response = self.download_image(file_id)

    def download_image(self, file_id):
        """ Downloads an image and returns a response. Returns None on failure
            or if there is nothing to say. Sets the channel. """
        # Get the file info from the File ID
        response = slack_client.api_call("files.info", file=str(file_id))
        if not response['ok']:
            return None
        user_id = response['file']['user']
        self.channel = user_id
        size = response['file']['size']
        filetype = response['file']['filetype']
        title = response['file']['title']
        if MAGIC_WORD not in title.lower():
            return None
        elif size > 1024 * 1000:
            return "I can't handle images more than a megabyte."
        elif filetype != "jpg" and filetype != "png":
            return "I can only handle PNGs and JPGs"

        # Download the file (with authentication)
        url = response['file']['url_private']
        header = {'Authorization': 'Bearer '+BOT_TOKEN}
        fileResponse = requests.post(url, headers=header)
        if not fileResponse.ok:
            return "I could not download the image at " + url

        # Where should the file go before we know its md5?
        subdir = get_username_from_id(user_id)
        output_dir = os.path.join('downloadedImages', subdir)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        tmp_filename = str(uuid.uuid4()) + '.' + filetype
        tmp_filepath = os.path.join(output_dir, tmp_filename)
        image_md5 = md5.new()

        # Read and save the file
        with open(tmp_filepath, 'wb') as handle:
            for block in fileResponse.iter_content(1024):
                handle.write(block)
                image_md5.update(block)

        # Now that we know the md5, move the file there
        output_filename = image_md5.hexdigest() + '.' + filetype
        output_filepath = os.path.join(output_dir, output_filename)
        shutil.move(tmp_filepath, output_filepath)

        upload_image(output_filepath)

        return "Thanks for the tip, friend! Don't forget " + output_filename

def create_js_list(file_list, output_filepath):
    """ Writes a javascript file containing a list of images outlined in
        file_list. Assumes there is only one avabot server running. """
    with open(output_filepath, 'wb') as myfile:
        myfile.write('function getImages() {\n')
        myfile.write('  return [\n')
        for i in file_list:
            if i:
                myfile.write('    "' + i + '",\n')
        myfile.write('] }')

def delete_file_from_filelist(localFile):
    with open(FILELIST_TXT, 'r') as myfile:
        lines = myfile.readlines()

    # Will throw a ValueError if the filename DNE
    lines.remove(localFile + '\n')

    with open(FILELIST_TXT, 'w') as myfile:
        myfile.writelines([item for item in lines[:-1]])

def write_file_to_filelist(localFile):
    with open(FILELIST_TXT, "a") as myfile:
        myfile.write(os.path.basename(localFile) + "\n")

def delete_image(localFile):
    upload_delete_helper(localFile, deleteMode=True)

def upload_image(localFile):
    upload_delete_helper(localFile, deleteMode=False)

def upload_delete_helper(localFile, deleteMode):
    """ Upload the image at localFile to the FTP_DIR with the same name. """
    with pysftp.Connection(FTP_URL, username=FTP_USER, password=FTP_PASS) as sftp:
        with sftp.cd(FTP_DIR):
            if deleteMode:
                sftp.remove(localFile)
                delete_file_from_filelist(localFile)
            else:
                sftp.put(localFile)
                write_file_to_filelist(localFile)

            # Add contents of uploadedFiles.txt to a js list
            with open(FILELIST_TXT, "r") as myfile:
                file_list = myfile.read().split('\n')
            output_filepath = FILELIST_JS
            create_js_list(file_list, output_filepath)
            sftp.put(output_filepath)

def handle_command(message):
    if message.response is None:
        print "Ignoring request of type ", message.type
        return

    print "Sending '" + message.response + "' to " + message.channel
    slack_client.api_call("chat.postMessage",
                          channel=message.channel,
                          text=message.response,
                          as_user=True)

def get_username_from_id(uid):
    """ Returns the username corresponding to the ID, or on failure,
        the user ID itself. """
    response = slack_client.api_call("users.info", user=uid)
    if not response['ok']:
        return uid
    else:
        return response['user']['name'] + "-" + uid

def parse_slack_output(slack_rtm_output):
    """ The Slack Real Time Messaging API is an events firehose.
        this parsing function returns None unless a message is
        directed at the Bot, based on its ID.  """
    output_list = slack_rtm_output
    if output_list and len(output_list) > 0:
        for output in output_list:
            if output['type'] == 'message' and 'text' in output:
                text = output['text']
                if text.startswith(AT_BOT):
                    return Message(type='text',
                                   channel=output['channel'],
                                   text=text.split(AT_BOT)[1].strip().lower())
            elif output['type'] == 'file_shared':
                file_id = output['file_id']
                return File(file_id=file_id)
    return None

if __name__ == "__main__":
    READ_WEBSOCKET_DELAY = 1 # 1 second delay between reading from firehose
    if slack_client.rtm_connect():
        print("Ava is listening")
        while True:
            try:
                message = parse_slack_output(slack_client.rtm_read())
            except websocket._exceptions.WebSocketConnectionClosedException:
                print "Web socket connection closed, attempting to reconnect."
                if not slack_client.rtm_connect():
                    print "Failed. Dying."
                    raise
            if message:
                handle_command(message)
            time.sleep(READ_WEBSOCKET_DELAY)
    else:
        print("Connection failed. Invalid Slack token or bot ID?")
