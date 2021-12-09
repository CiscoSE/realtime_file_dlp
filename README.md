# Webex Real-time File DLP Example
This is an example of how [Webex Real-time File DLP](https://developer.webex.com/docs/api/guides/webex-real-time-file-dlp-basics) can be used. The DLP allows to scan files posted to Webex Space before they are available for download.
It's a great improvement, because traditional DLP is reactive, no matter if it's Webex, O365 or Google - file is first
stored in the cloud service, then scanned by a DLP system and eventually removed. Real-time DLP removes this limitation and reduces the risk of data loss.

This example checks the MIME type of the files and if it doesn't match regular a expression from **ALLOWED_MIME_TYPES_REGEX** variable, it's rejected. In the example, only images are approved.

In order to gain access to users' content, the application needs to run with [Compliance](https://developer.webex.com/docs/compliance) Officer's permissions. It runs as an [Integration](https://developer.webex.com/docs/integrations) and implements [OAuth Grant Flow](https://developer.webex.com/blog/real-world-walkthrough-of-building-an-oauth-webex-integration) to securely receive OAuth tokens with just a limited scope that is needed for file scanning.

## How it works
Following diagram describes how a file is posted and how an external DLP application can intercept its publication in a Space:

<img src="./images/arch_1.png" width="70%">

DLP application needs to have its [webhook](https://developer.webex.com/docs/webhooks) URL accessible via public Internet. The webhook receives a HTTP POST from Webex with the list of file URLs.
The application needs to respond within 10 seconds, otherwise the file is posted in the Space anyway with indication
that it has not been scanned. The response has to be in a form of HTTP GET or HEAD to the file URL with additional parameter **dlpUnchecked**. For example if the file URL is
```
https://webexapis.com/v1/contents/Y2lzY29zcGFyazovL3VybjpURUFNOnVzLXdlc3QtMl9yL0NPTlRFTlQvNWI1NzAyZjAtMmJhNS0xMWVjLWIyYWUtNmQwNjAwMzBkYTg2LzA?allow=dlpEvaluating
```
the GET/HEAD should be to
```
https://webexapis.com/v1/contents/Y2lzY29zcGFyazovL3VybjpURUFNOnVzLXdlc3QtMl9yL0NPTlRFTlQvNWI1NzAyZjAtMmJhNS0xMWVjLWIyYWUtNmQwNjAwMzBkYTg2LzA?allow=dlpEvaluating,dlpUnchecked
```
This example is using HTTP HEAD to read the MIME type. It saves time and also doesn't store unwanted copies of users' content.
HTTP GET can be used to get a full copy of the file and perform scanning of its content. For example for viruses
or confidential information.

Once the decision has been made, the DLP application has to respond with HTTP PUT to file URL with parameter **result** with value of **reject** or **approve**. For example:
```
https://webexapis.com/v1/contents/Y2lzY29zcGFyazovL3VybjpURUFNOnVzLXdlc3QtMl9yL0NPTlRFTlQvNWI1NzAyZjAtMmJhNS0xMWVjLWIyYWUtNmQwNjAwMzBkYTg2LzA?result=reject
```
or
```
https://webexapis.com/v1/contents/Y2lzY29zcGFyazovL3VybjpURUFNOnVzLXdlc3QtMl9yL0NPTlRFTlQvNWI1NzAyZjAtMmJhNS0xMWVjLWIyYWUtNmQwNjAwMzBkYTg2LzA?result=approve
```

All the above GET/HEAD/PUT requests have to be authorized by a proper OAuth Access Token. The token has to be issued
for at least **spark-compliance:messages_read** and **spark-compliance:messages_write** scopes. The example uses also
**spark-compliance:rooms_read, spark-compliance:webhooks_read, spark-compliance:webhooks_write** (see **FILES_COMPLIANCE_SCOPE** variable) in order to manage the webhook and get information about the Space.
