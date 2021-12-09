# Webex Real-time File DLP Example
This is an example of how [Webex Real-time File DLP](https://developer.webex.com/docs/api/guides/webex-real-time-file-dlp-basics) can be used. The DLP allows to scan files posted to Webex Space before they are available for download.
It's a great improvement, because traditional DLP is reactive, no matter if it's Webex, O365 or Google - file is first
stored in the cloud service, then scanned by a DLP system and eventually removed. Real-time DLP removes this limitation and reduces the risk of data loss.
## How it works
Following diagram describes how a file is posted and how an external DLP application can intercept its publication in a Space:
<img src="./images/arch_1.png" width="70%">
DLP application needs to have its [webhook](https://developer.webex.com/docs/webhooks) URL accessible via public Internet. The webhook receives a HTTP POST from Webex with the list of file URLs.
The application needs to respond within 10 seconds, otherwise the file is posted in the Space anyway with an indication
that it has not been scanned. The response can be in a form of HTTP GET or HEAD to the file URL with additional parameter
**dlpUnchecked**. For example if the file URL is
```
https://webexapis.com/v1/contents/Y2lzY29zcGFyazovL3VybjpURUFNOnVzLXdlc3QtMl9yL0NPTlRFTlQvNWI1NzAyZjAtMmJhNS0xMWVjLWIyYWUtNmQwNjAwMzBkYTg2LzA?allow=dlpEvaluating
```
the GET/HEAD should be to
```
https://webexapis.com/v1/contents/Y2lzY29zcGFyazovL3VybjpURUFNOnVzLXdlc3QtMl9yL0NPTlRFTlQvNWI1NzAyZjAtMmJhNS0xMWVjLWIyYWUtNmQwNjAwMzBkYTg2LzA?allow=dlpEvaluating,dlpUnchecked
```
