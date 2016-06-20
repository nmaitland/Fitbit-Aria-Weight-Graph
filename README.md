Fitbit Aria Weight Graph
======

Python desktop app that uses wxPython and matplotlib to display a plot of weight over time, including a nice average for a better idea of progress.

You'll need to make a config.ini file which matches the following template:

 ```
[oauth]
client_ID = yourclientidhere
client_secret = yourclientsecrethere
```

Values for `client_id` and `client_secret` can be found if you register an app on the [Fitbit developer site]("https://dev.fitbit.com/apps") then:
- Select "MANAGE MY APPS", select your app and find your "OAuth 2.0 Client ID". 
- Find your "Client Secret"