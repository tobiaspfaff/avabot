Avabot uploads files from Slack to an FTP server.

To trigger an upload, Ava must be subscribed to a channel and the user must include the magic word in the file's title.

To run avabot.py, you must define the following environment variables:

```bash
export SLACK_BOT_TOKEN='<secret token from slack>'
export BOT_ID='<output of print_bot_id.py>'
export FTP_URL='<sftp hostname of where to upload the files>'
export FTP_USER='<sftp username>'
export FTP_PASS='<sftp password>'
export FTP_DIR='<sftp directory in which to store files>'
export MAGIC_WORD='<word that triggers an upload>'
```

You must define your SLACK_BOT_TOKEN before obtaining your BOT_ID.

Images are locally stored in downloadedImages/user_name-user_id/uuid.{png,jpg}.
