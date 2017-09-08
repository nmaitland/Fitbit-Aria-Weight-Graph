import wx
import matplotlib
matplotlib.use("WxAgg")
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wx import NavigationToolbar2Wx, wxc
from matplotlib.figure import Figure
from matplotlib import pyplot as plt
from matplotlib import dates
from matplotlib.widgets import Cursor
from matplotlib.collections import LineCollection

from numpy import array, convolve, diff, linspace, concatenate, ones, arange

from scipy.interpolate import InterpolatedUnivariateSpline

from datetime import datetime

import fitbit

import configparser

from gather_keys_oauth2 import OAuth2Server
from savitzky_golay import savitzky_golay

import os
__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

ranges = [(  '2 Weeks', 14), 
            ('Month', 30), 
            ('3 Months', 90),
            ('6 Months', 180),
            ('Year', 365),
            ('All time', 0)
        ]

class FitbitPlot(object):
    def __init__(self, parent):
        self.figure = Figure(figsize=(16, 10))
        self.axes = self.figure.add_subplot(111)

        self.figure.set_tight_layout(True)

        self.canvas = FigureCanvas(parent, -1, self.figure)

        self.axes.text(0.5, 0.5, "Choose a time period from above",ha='center')

        self.has_fetched = False

    def authenticate(self):
        parser = configparser.ConfigParser()
        parser.read(os.path.join(__location__, 'config.ini'))

        client_ID = parser.get('oauth', 'client_ID')
        client_secret = parser.get('oauth', 'client_secret')

        # Authenticate with Fitbit
        print("Authenticating with Fitbit")
        try:
            f = open(os.path.join(__location__, 'auth'), 'r')
            try:
                lines = f.read().splitlines()
                try:
                    self.access_token = lines[0]
                    self.refresh_token = lines[1]
                except IndexError:
                    self.get_tokens(client_ID, client_secret)
            finally:
                f.close()
            self.get_tokens(client_ID, client_secret, self.access_token, self.refresh_token)
        except (IOError, FileNotFoundError):
            print("Failed to open auth file")
            self.get_tokens(client_ID, client_secret)


        self.authd_client = fitbit.Fitbit(client_ID, client_secret, access_token=self.access_token, refresh_token=self.refresh_token, system='en_AU')
        print("Client successfully authenticated")

    def get_tokens(self, client_ID, client_secret, access_token=None, refresh_token=None):
        if (access_token==None or refresh_token==None):
            print("Authenticating with browser.")
            server = OAuth2Server(client_ID, client_secret)
            server.browser_authorize()
            token = server.fitbit.client.session.token
            self.access_token = token['access_token']
            self.refresh_token = token['refresh_token']
        else:
            print("Authenticating with old access and refesh tokens")
            auth = fitbit.FitbitOauth2Client(client_ID, client_secret, access_token, refresh_token)
            auth.refresh_token()
            self.access_token = access_token
            self.refresh_token = refresh_token      

        f = open(os.path.join(__location__, 'auth'), 'w')
        f.write(self.access_token + "\n" + self.refresh_token)
        f.close()
        print("New auth file written")

    # Handle clicking on radio buttons
    def change_time_period(self, tp):
        if not self.has_fetched:
            self.get_data()
            self.has_fetched = True
        if tp == 'All time':
            offset = int(max(self.date)-min(self.date))
        else:
            offset = [t[1] for t in ranges if t[0] == tp][0]
        self.plot(offset)
        
        x_min = max(self.date)-offset
        x_max = max(self.date)
        min_date_index = min(range(len(self.date)), key=lambda i: abs(self.date[i]-x_min))
        y_min = min(self.weight[min_date_index:])
        y_max = max(self.weight[min_date_index:])
        self.axes.set_xlim(x_min-(x_max-x_min)*0.01,x_max+(x_max-x_min)*0.01)
        self.axes.set_ylim(y_min-(y_max-y_min)*0.01,y_max+(y_max-y_min)*0.01)

        self.figure.canvas.draw_idle()

    def get_data(self):
        wait = wx.BusyCursor()
        # Pull all bodyweight data
        try:
            # Try 5 times
            for i in range(5):
                try:
                    bodyweight = self.authd_client.time_series(resource='body/weight', base_date='2015-01-01', end_date='today')
                except AttributeError:
                    self.authenticate()
                    continue
                break
            # Split data to date and weight lists
            self.date=[]
            weight=[]
            for entry in bodyweight['body-weight']:
                dt = datetime.strptime(entry['dateTime'], '%Y-%m-%d')
                self.date.append(dates.date2num(dt))
                weight.append(entry['value'])

            self.weight = array(weight,dtype=float)
        except fitbit.exceptions.HTTPUnauthorized:
            print("Unauthorized. Reauthenticating...")
            open(os.path.join(__location__, 'auth'), 'w').close()
            self.authenticate()
        del wait


    def plot(self, N=14):
        # Smooth time series
        window_size = N/2+1 if (N/2)%2==0 else N/2
        smoothed = savitzky_golay(self.weight, window_size , 3).tolist()[-N-5:]
        x=self.date[-N-5:]

        # Find slope for colouration of interped line
        slope = diff(smoothed)

        print(len(x), len (slope))
        f = InterpolatedUnivariateSpline(x, smoothed,ext=1)
        f_slope = InterpolatedUnivariateSpline([a+(x[1]-x[0])/2 for a in x[:-1]], slope,k=1)
        x_interp = linspace(min(x), max(x), num=1000, endpoint=True)

        # Create a set of line segments so that we can color them individually
        # This creates the points as a N x 1 x 2 array so that we can stack points
        # together easily to get the segments. The segments array for line collection
        # needs to be numlines x points per line x 2 (x and y)
        points = array([x_interp, f(x_interp)]).T.reshape(-1, 1, 2)
        segments = concatenate([points[:-1], points[1:]], axis=1)

        # Colour average based on slope
        self.coloured_line = LineCollection(segments, cmap=plt.get_cmap('RdYlBu_r'),
            norm=plt.Normalize(-max(slope), max(slope)))
        self.coloured_line.set_array(f_slope(x_interp))
        self.coloured_line.set_linewidth(5)
        self.coloured_line.set_label('Moving average (%d days)'%N)

        # Plot actual data
        self.axes.plot_date(self.date, self.weight, '-', label='Logged weight',zorder=1, color='darkgrey', linewidth=1)
        # Plot smoothed line
        try:
            self.figure.gca().collections.remove(self.col)
        except AttributeError: 
            pass
        finally:
            self.col = self.figure.gca().add_collection(self.coloured_line)

        # Axis label formatting
        date_locator = dates.AutoDateLocator()
        date_formatter = dates.AutoDateFormatter(date_locator)
        self.axes.get_xaxis().set_major_locator(date_locator)
        self.axes.get_xaxis().set_major_formatter(date_formatter)
        self.axes.set_xlabel('Date')
        self.axes.set_ylabel('Weight')
        self.axes.set_title('Fitbit Aria log')

        # # Custom mouseover and mouse crosshair
        # def format_coord(x, y):
        #   closest_date = min(self.date, key=lambda l:abs(l-x))
        #   return 'date='+dates.num2date(x).strftime('%d/%m/%Y') + ', weight=%1.1f '%float(self.weight[self.date.index(closest_date)])
        # self.axes.format_coord = format_coord

        # self.figure.autofmt_xdate()
        # cursor = Cursor(self.axes, useblit=True, horizOn=False, color='grey', linewidth=1 )

class CanvasFrame(wx.Frame):
    def __init__(self, parent, title):
        wx.Frame.__init__(self, parent, -1, title, pos=wx.GetMousePosition(), size=wx.Size(800, 300))
        self.SetBackgroundColour(wxc.NamedColour("WHITE"))

        self.fitbit_plot = FitbitPlot(self)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.add_buttonbar()
        self.sizer.Add(self.fitbit_plot.canvas, 1, wx.LEFT | wx.TOP | wx.GROW)
        #self.add_toolbar()  # comment this out for no toolbar

        self.SetSizer(self.sizer)
        self.Fit()

    def add_buttonbar(self):
        self.button_bar = wx.Panel(self)
        self.button_bar_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.sizer.Add(self.button_bar, 0, wx.LEFT | wx.TOP | wx.GROW)

        for i, text in enumerate(ranges):
            button = wx.Button(self.button_bar, i, text[0])
            button.name = text[0]
            self.button_bar_sizer.Add(button, 1, wx.GROW)
            self.Bind(wx.EVT_BUTTON, self.OnClick, button)

        self.button_bar.SetSizer(self.button_bar_sizer)

    def OnClick(self, event):
        name = event.GetEventObject().name
        self.fitbit_plot.change_time_period(name)

    def add_toolbar(self):
        """Copied verbatim from embedding_wx2.py"""
        self.toolbar = NavigationToolbar2Wx(self.fitbit_plot.canvas)
        self.toolbar.Realize()
        # By adding toolbar in sizer, we are able to put it at the bottom
        # of the frame - so appearance is closer to GTK version.
        self.sizer.Add(self.toolbar, 0, wx.LEFT | wx.EXPAND)
        # update the axes menu on the toolbar
        self.toolbar.update()

class MyApp(wx.App):
    def OnInit(self):
        frame = CanvasFrame(None, "Fitbit Aria Weight Log")
        self.SetTopWindow(frame)
        frame.Show(True)
        frame.Maximize(True)
        return True

app = MyApp()
app.MainLoop()