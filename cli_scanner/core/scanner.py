"""
Earnings scanner that handles date logic and filtering.
"""

import logging
import re
import time
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor

import pytz
import requests
from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import yfinance as yf
from tqdm import tqdm

from .analyzer import OptionsAnalyzer
import core.yfinance_cookie_patch

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

core.yfinance_cookie_patch.patch_yfdata_cookie_basic()
session = curl_requests.Session(impersonate="chrome")

class EarningsScanner:
    # Initialize class variables, only one __init__ method should exist
    def __del__(self):
        # Clean up browser when scanner is destroyed
        if hasattr(self, '_driver') and self._driver is not None:
            try:
                self._driver.quit()
            except Exception as e:
                # Just silently ignore errors during cleanup
                pass
                
    def calculate_iron_fly_strikes(self, ticker: str) -> Dict[str, any]:
        """
        Calculate recommended iron fly strikes based on options closest to 50 delta.
        
        Returns a dictionary containing:
        - short_call_strike: Strike price of the short call (near 50 delta)
        - short_put_strike: Strike price of the short put (near 50 delta)
        - long_call_strike: Strike price of the long call (wing)
        - long_put_strike: Strike price of the long put (wing)
        - short_call_premium: Premium received for short call
        - short_put_premium: Premium received for short put
        - total_credit: Total credit received for the short strikes
        - wing_width: The width used for the wings (3x credit)
        """
        try:
            # Get ticker data
            ticker_obj = yf.Ticker(ticker, session=session)
            if not ticker_obj.options or len(ticker_obj.options) == 0:
                return {"error": "No options available"}
            
            # Get the nearest expiration
            expiry = ticker_obj.options[0]
            
            # Get the options chain
            opt_chain = ticker_obj.option_chain(expiry)
            calls = opt_chain.calls
            puts = opt_chain.puts
            
            # Current price
            current_price = ticker_obj.history(period='1d')['Close'].iloc[-1]
            
            # Check if delta column exists
            if 'delta' in calls.columns and 'delta' in puts.columns:
                # Find call closest to 50 delta (absolute value)
                calls['delta_diff'] = abs(abs(calls['delta']) - 0.5)
                closest_call = calls.loc[calls['delta_diff'].idxmin()]
                short_call_strike = closest_call['strike']
                short_call_premium = (closest_call['bid'] + closest_call['ask']) / 2
                
                # Find put closest to 50 delta (absolute value)
                puts['delta_diff'] = abs(abs(puts['delta']) - 0.5)
                closest_put = puts.loc[puts['delta_diff'].idxmin()]
                short_put_strike = closest_put['strike']
                short_put_premium = (closest_put['bid'] + closest_put['ask']) / 2
            else:
                # If delta not available, use strike closest to current price
                # Find call closest to ATM
                calls['price_diff'] = abs(calls['strike'] - current_price)
                closest_call = calls.loc[calls['price_diff'].idxmin()]
                short_call_strike = closest_call['strike']
                short_call_premium = (closest_call['bid'] + closest_call['ask']) / 2
                
                # Find put closest to ATM
                puts['price_diff'] = abs(puts['strike'] - current_price)
                closest_put = puts.loc[puts['price_diff'].idxmin()]
                short_put_strike = closest_put['strike']
                short_put_premium = (closest_put['bid'] + closest_put['ask']) / 2
            
            # Calculate total credit
            total_credit = short_call_premium + short_put_premium
            
            # Calculate wing width - 3x the credit received
            wing_width = 3 * total_credit
            
            # Calculate wing strikes
            long_put_strike = short_put_strike - wing_width
            long_call_strike = short_call_strike + wing_width
            
            # Find actual option strikes that are closest to calculated wings
            available_put_strikes = sorted(puts['strike'].unique())
            available_call_strikes = sorted(calls['strike'].unique())
            
            # Find closest available strikes for wings
            long_put_strike = min(available_put_strikes, key=lambda x: abs(x - long_put_strike))
            long_call_strike = min(available_call_strikes, key=lambda x: abs(x - long_call_strike))
            
            # Find prices for long positions
            long_put_option = puts[puts['strike'] == long_put_strike].iloc[0]
            long_call_option = calls[calls['strike'] == long_call_strike].iloc[0]
            long_put_premium = round((long_put_option['bid'] + long_put_option['ask']) / 2, 2)
            long_call_premium = round((long_call_option['bid'] + long_call_option['ask']) / 2, 2)
            
            # Calculate actual wing widths
            put_wing_width = short_put_strike - long_put_strike
            call_wing_width = long_call_strike - short_call_strike
            
            # Calculate max profit and max risk
            total_debit = long_put_premium + long_call_premium
            net_credit = total_credit - total_debit
            max_profit = net_credit
            max_risk = min(put_wing_width, call_wing_width) - net_credit
            
            # Calculate break-even points
            upper_breakeven = short_call_strike + net_credit
            lower_breakeven = short_put_strike - net_credit
            
            # Calculate risk-reward ratio
            risk_reward_ratio = round(max_risk / max_profit, 1) if max_profit > 0 else float('inf')
            
            # Round values for display
            short_call_strike = round(short_call_strike, 2)
            short_put_strike = round(short_put_strike, 2)
            long_call_strike = round(long_call_strike, 2)
            long_put_strike = round(long_put_strike, 2)
            short_call_premium = round(short_call_premium, 2)
            short_put_premium = round(short_put_premium, 2)
            total_credit = round(total_credit, 2)
            put_wing_width = round(put_wing_width, 2)
            call_wing_width = round(call_wing_width, 2)
            max_profit = round(max_profit, 2)
            max_risk = round(max_risk, 2)
            
            return {
                "short_call_strike": short_call_strike,
                "short_put_strike": short_put_strike,
                "long_call_strike": long_call_strike,
                "long_put_strike": long_put_strike,
                "short_call_premium": short_call_premium,
                "short_put_premium": short_put_premium,
                "long_call_premium": long_call_premium,
                "long_put_premium": long_put_premium,
                "total_credit": round(total_credit, 2),
                "total_debit": round(total_debit, 2),
                "net_credit": round(net_credit, 2),
                "put_wing_width": put_wing_width,
                "call_wing_width": call_wing_width,
                "max_profit": max_profit,
                "max_risk": max_risk,
                "upper_breakeven": round(upper_breakeven, 2),
                "lower_breakeven": round(lower_breakeven, 2),
                "risk_reward_ratio": risk_reward_ratio,
                "expiration": expiry
            }
        except Exception as e:
            logger.warning(f"Error calculating iron fly for {ticker}: {e}")
            return {"error": str(e)}
    
    def get_scan_dates(self, input_date: Optional[str] = None) -> Tuple[datetime.date, datetime.date]:
        if input_date:
            try:
                post_date = datetime.strptime(input_date, '%m/%d/%Y').date()
                pre_date = post_date + timedelta(days=1)
                logger.info(f"Using provided date: post-market {post_date}, pre-market {pre_date}")
            except ValueError as e:
                logger.error(f"Invalid date format: {e}")
                raise ValueError("Please provide date in MM/DD/YYYY format")
        else:
            now = datetime.now(self.eastern_tz)
            market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
            post_date = now.date() if now < market_close else (now + timedelta(days=1)).date()
            pre_date = post_date + timedelta(days=1)

        return post_date, pre_date

    def _get_dolthub_earnings_data(self, date: datetime.date) -> List[Dict]:
        """
        Get earnings data from DoltHub's post-no-preference/earnings database.
        Added robust error handling and memory management to prevent segmentation faults.
        
        Args:
            date: The date to fetch earnings for
            
        Returns:
            List of dictionaries with ticker and timing information
        """
        # Check if mysql-connector is installed
        try:
            import mysql.connector
            from mysql.connector import errorcode
        except ImportError:
            logger.warning("mysql-connector-python not installed. Run 'pip install mysql-connector-python' to use DoltHub data.")
            logger.info("Falling back to other sources due to missing mysql-connector")
            return []
        
        # Format date for SQL query (YYYY-MM-DD)
        formatted_date = date.strftime('%Y-%m-%d')
        conn = None
        cursor = None
        
        try:
            # Connect to DoltHub's MySQL interface with enhanced error handling
            logger.info(f"Connecting to DoltHub earnings database for {formatted_date}")
            
            # Use a try-except block with specific error codes
            try:
                config = {
                    'host': 'localhost',
                    'port': 3306,
                    'user': 'root',
                    'password': '',
                    'database': 'earnings',
                    'connection_timeout': 5,  # Shorter timeout to fail faster
                    'buffered': True,         # Use buffered cursor
                    'use_pure': True,         # Use pure Python implementation for better stability
                    'autocommit': True,       # Avoid transaction issues
                    'get_warnings': True,     # Get warnings for better debugging
                    'raise_on_warnings': False # Don't raise on warnings
                    # Removed 'connection_attributes' parameter that was causing errors
                }
                
                conn = mysql.connector.connect(**config)
                
                # Check if connection was successful (explicit check after connection)
                if not conn.is_connected():
                    logger.error("Failed to connect to MySQL server - connection not established")
                    return []
                    
            except mysql.connector.Error as err:
                if err.errno == errorcode.CR_CONN_HOST_ERROR:
                    logger.error(f"Failed to connect to MySQL server - host error: {err}")
                elif err.errno == errorcode.CR_SERVER_GONE_ERROR or err.errno == errorcode.CR_SERVER_LOST:
                    logger.error(f"MySQL server connection lost: {err}")
                elif err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                    logger.error(f"MySQL access denied: {err}")
                elif err.errno == errorcode.ER_BAD_DB_ERROR:
                    logger.error(f"MySQL database 'earnings' does not exist: {err}")
                else:
                    logger.error(f"MySQL connection error: {err}")
                logger.info("Falling back to other sources due to MySQL connection issues")
                return []
            except Exception as e:
                logger.error(f"Unexpected error connecting to MySQL: {e}")
                logger.info("Falling back to other sources due to connection error")
                return []
            
            try:
                # Create cursor with dictionary=True for named column access
                cursor = conn.cursor(dictionary=True)
                
                # Set session variables for safety
                cursor.execute("SET SESSION max_execution_time=5000")  # 5 second timeout
                cursor.execute("SET SESSION sql_mode='STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ENGINE_SUBSTITUTION'")
            except mysql.connector.Error as err:
                logger.error(f"Error creating cursor: {err}")
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
                logger.info("Falling back to other sources due to cursor creation error")
                return []
                
            # Query the earnings_calendar table for the specified date
            query = "SELECT act_symbol, `when` FROM earnings_calendar WHERE date = %s"
            
            # Execute the query with parameterized input and proper error handling
            try:
                cursor.execute(query, (formatted_date,))
                
                # Fetch data with explicit error handling
                try:
                    rows = cursor.fetchall()
                except mysql.connector.Error as err:
                    logger.error(f"Error fetching results: {err}")
                    return []
                    
            except mysql.connector.Error as err:
                if err.errno == errorcode.CR_SERVER_GONE_ERROR or err.errno == errorcode.CR_SERVER_LOST:
                    logger.error(f"Lost connection to MySQL server during query: {err}")
                else:                
                    logger.error(f"Error executing query: {err}")
                return []
            
            # Map the results to our expected format with proper error handling for each row
            stocks = []
            for row in rows:
                try:
                    # Defensive programming - verify keys exist
                    if 'act_symbol' not in row or row['act_symbol'] is None:
                        continue
                        
                    ticker = row['act_symbol']
                    when = row.get('when', None)  # Use get() to safely handle missing keys
                    
                    # Normalize timing with clear mapping
                    if when == "Before market open" or when == "bmo":
                        timing = "Pre Market"
                    elif when == "After market close" or when == "amc":
                        timing = "Post Market"
                    elif when is None:
                        timing = "Unknown"
                    else:
                        timing = "During Market"
                    
                    # Only add if we have valid ticker
                    if ticker and ticker.strip():
                        stocks.append({'ticker': ticker.strip(), 'timing': timing})
                except Exception as e:
                    logger.debug(f"Error processing row for ticker data: {e}")
                    # Continue processing other rows
            
            logger.info(f"Found {len(stocks)} earnings reports from DoltHub")
            return stocks
            
        except Exception as e:
            logger.error(f"Unexpected error fetching data from DoltHub: {e}")
            logger.info("Falling back to other sources due to unexpected error")
            return []
        finally:
            # Enhanced cleanup with separate try-except blocks for cursor and connection
            if cursor:
                try:
                    cursor.close()
                    logger.debug("MySQL cursor closed")
                except Exception as e:
                    logger.debug(f"Error closing MySQL cursor: {e}")
                    
            if conn:
                try:
                    if conn.is_connected():
                        conn.close()
                        logger.debug("MySQL connection closed")
                except Exception as e:
                    logger.debug(f"Error closing MySQL connection: {e}")
            
    def _get_finnhub_earnings_data(self, date: datetime.date) -> List[Dict]:
        """
        Get earnings data from Finnhub API.
        
        This requires a free Finnhub API key to be set as an environment variable FINNHUB_API_KEY.
        Register for free at https://finnhub.io/ to obtain an API key.
        
        Args:
            date: The date to fetch earnings for
            
        Returns:
            List of dictionaries with ticker and timing information
        """
        import os
        import requests
        
        api_key = os.environ.get('FINNHUB_API_KEY')
        if not api_key:
            logger.warning("FINNHUB_API_KEY environment variable not set. Cannot use Finnhub as fallback.")
            return []
            
        # Format date for Finnhub (YYYY-MM-DD)
        formatted_date = date.strftime('%Y-%m-%d')
        
        url = f"https://finnhub.io/api/v1/calendar/earnings"
        params = {
            'from': formatted_date,
            'to': formatted_date,
            'token': api_key
        }
        
        try:
            logger.info(f"Fetching earnings data from Finnhub for {formatted_date}")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if 'earningsCalendar' not in data:
                logger.warning("Invalid response format from Finnhub API")
                return []
                
            stocks = []
            for entry in data['earningsCalendar']:
                try:
                    ticker = entry.get('symbol')
                    if not ticker:
                        continue
                        
                    # Get time information - Finnhub provides hour in 'hour' field
                    hour = entry.get('hour', '').lower()
                    
                    if hour == 'bmo':  # Before Market Open
                        timing = 'Pre Market'
                    elif hour == 'amc':  # After Market Close
                        timing = 'Post Market'
                    elif hour in ['dmh', '']:  # During Market Hours or unknown
                        timing = 'During Market'
                    else:
                        timing = 'Unknown'
                    
                    stocks.append({'ticker': ticker, 'timing': timing})
                except Exception as e:
                    logger.debug(f"Error processing Finnhub entry for {ticker}: {e}")
            
            logger.info(f"Found {len(stocks)} earnings reports from Finnhub")
            return stocks
            
        except Exception as e:
            logger.warning(f"Error fetching data from Finnhub: {e}")
            return []
    
    def _get_fallback_earnings_data(self, date: datetime.date) -> List[Dict]:
        """
        Fallback method to get earnings data when the primary source fails.
        Uses Finnhub API as a backup source.
        """
        return self._get_finnhub_earnings_data(date)
    
    # Initialize class variables, only one __init__ method should exist
    def __init__(self, eastern_tz=pytz.timezone('US/Eastern')):  # Constructor with eastern timezone parameter
        # Default parameter values initialization
        self.eastern_tz = eastern_tz
        self.batch_size = 8  # Default batch size
        # Default threshold values for IV/RV ratio
        self.iv_rv_pass_threshold = 1.25
        self.iv_rv_near_miss_threshold = 1.0
        # Initialize the analyzer
        self.analyzer = OptionsAnalyzer()
    
    def _get_combined_earnings_data(self, date: datetime.date) -> List[Dict]:
        """
        Get earnings data from all available sources and combine results.
        
        This method fetches data from DoltHub, Finnhub, and Investing.com,
        then merges the results to get a comprehensive list of unique stocks.
        
        Args:
            date: The date to fetch earnings for
            
        Returns:
            List of dictionaries with ticker and timing information with duplicates removed
        """
        logger.info(f"Fetching earnings data from all sources for {date}")
        
        # Get data from all sources
        dolthub_stocks = self._get_dolthub_earnings_data(date)
        finnhub_stocks = self._get_finnhub_earnings_data(date)
        investing_stocks = self._get_investing_earnings_data(date)
        
        logger.info(f"Found {len(dolthub_stocks)} from DoltHub, {len(finnhub_stocks)} from Finnhub, "  
                   f"and {len(investing_stocks)} from Investing.com")
        
        # Create a dictionary to merge the results, using the ticker as the key
        all_stocks = {}
        
        # Process stocks from each source in order of preference
        # DoltHub first (seems most accurate based on user feedback)
        for stock in dolthub_stocks:
            ticker = stock['ticker']
            all_stocks[ticker] = stock
        
        # Then Finnhub stocks
        for stock in finnhub_stocks:
            ticker = stock['ticker']
            if ticker not in all_stocks:
                all_stocks[ticker] = stock
            # Keep DoltHub timing if it exists, but if DoltHub was Unknown and Finnhub has a value, use Finnhub's
            elif all_stocks[ticker].get('timing') == 'Unknown' and stock.get('timing') != 'Unknown':
                all_stocks[ticker]['timing'] = stock.get('timing')
        
        # Finally Investing.com stocks
        for stock in investing_stocks:
            ticker = stock['ticker']
            if ticker not in all_stocks:
                all_stocks[ticker] = stock
            # Only override timing if current is Unknown and new one isn't
            elif all_stocks[ticker].get('timing') == 'Unknown' and stock.get('timing') != 'Unknown':
                all_stocks[ticker]['timing'] = stock.get('timing')
                
        # Convert back to a list
        merged_stocks = list(all_stocks.values())
        
        logger.info(f"Combined {len(dolthub_stocks)} + {len(finnhub_stocks)} + {len(investing_stocks)} = {len(merged_stocks)} unique stocks")
        
        return merged_stocks
    
    def fetch_earnings_data(self, date: datetime.date) -> List[Dict]:
        # Check if we should use all sources combined
        if getattr(self, 'all_sources', False):
            logger.info("Using ALL data sources combined (DoltHub + Finnhub + Investing.com)")
            return self._get_combined_earnings_data(date)
            
        # Otherwise, follow the original source selection logic
        if getattr(self, 'use_dolthub', False):
            logger.info("Using DoltHub AND Finnhub as earnings data sources")
            
            # Get data from both sources
            dolthub_stocks = []
            finnhub_stocks = []
            
            # Try to get DoltHub data
            try:
                dolthub_stocks = self._get_dolthub_earnings_data(date)
                logger.info(f"Found {len(dolthub_stocks)} stocks from DoltHub")
            except Exception as e:
                logger.error(f"Error using DoltHub: {e}")
            
            # Try to get Finnhub data (regardless of whether DoltHub worked)
            try:
                finnhub_stocks = self._get_finnhub_earnings_data(date)
                logger.info(f"Found {len(finnhub_stocks)} stocks from Finnhub")
            except Exception as e:
                logger.error(f"Error using Finnhub: {e}")
            
            # Combine results (simple merge with deduplication)
            all_stocks = {}
            
            # Add DoltHub stocks first
            for stock in dolthub_stocks:
                ticker = stock['ticker']
                all_stocks[ticker] = stock
            
            # Add Finnhub stocks (avoiding duplicates)
            for stock in finnhub_stocks:
                ticker = stock['ticker']
                if ticker not in all_stocks:
                    all_stocks[ticker] = stock
                # If both have timing info, prefer non-Unknown timing
                elif all_stocks[ticker].get('timing') == 'Unknown' and stock.get('timing') != 'Unknown':
                    all_stocks[ticker]['timing'] = stock.get('timing')
            
            merged_stocks = list(all_stocks.values())
            logger.info(f"Combined {len(dolthub_stocks)} (DoltHub) + {len(finnhub_stocks)} (Finnhub) = {len(merged_stocks)} unique stocks")
            
            # If we found any stocks, return them
            if merged_stocks:
                return merged_stocks
            
            # If both DoltHub and Finnhub failed, fall back to Investing.com
            logger.info("Both DoltHub and Finnhub returned no data or failed, trying Investing.com as fallback")
            return self._get_investing_earnings_data(date)
        elif getattr(self, 'use_finnhub', False):
            logger.info("Using Finnhub as primary earnings data source")
            stocks = self._get_finnhub_earnings_data(date)
            # Only if Finnhub fails, try Investing.com as fallback
            if not stocks:
                logger.info("Finnhub returned no data, trying Investing.com as fallback")
                return self._get_investing_earnings_data(date)
            return stocks
        
        # Otherwise, use the original behavior (Investing.com primary, Finnhub fallback)
        return self._get_investing_earnings_data(date)
    
    def _get_investing_earnings_data(self, date: datetime.date) -> List[Dict]:
        """Get earnings data from Investing.com"""
        url = "https://www.investing.com/earnings-calendar/Service/getCalendarFilteredData"
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://www.investing.com/earnings-calendar/'
        }
        
        payload = {
            'country[]': '5',
            'dateFrom': date.strftime('%Y-%m-%d'),
            'dateTo': date.strftime('%Y-%m-%d'),
            'currentTab': 'custom',
            'limit_from': 0
        }
        
        try:
            # Add a user-agent rotation to avoid blocking
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
                'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
            ]
            import random
            headers['User-Agent'] = random.choice(user_agents)
            
            response = requests.post(url, headers=headers, data=payload, timeout=10)
            response.raise_for_status()  # Raise an exception for HTTP errors
            
            # Try to parse JSON response
            data = response.json()
            
            # Check if data has the expected structure
            if 'data' not in data:
                logger.warning("Invalid response format from Investing.com API")
                return self._get_fallback_earnings_data(date)
                
            soup = BeautifulSoup(data['data'], 'html.parser')
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Error fetching earnings data: {e}")
            return self._get_fallback_earnings_data(date)
        
        rows = soup.find_all('tr')
        
        stocks = []
        for row in rows:
            if not row.find('span', class_='earnCalCompanyName'):
                continue
            
            try:
                ticker = row.find('a', class_='bold').text.strip()
                timing_span = row.find('span', class_='genToolTip')
                
                if timing_span and 'data-tooltip' in timing_span.attrs:
                    tooltip = timing_span['data-tooltip']
                    if tooltip == 'Before market open':
                        timing = 'Pre Market'
                    elif tooltip == 'After market close':
                        timing = 'Post Market'
                    else:
                        timing = 'During Market'
                else:
                    timing = 'Unknown'
                
                stocks.append({'ticker': ticker, 'timing': timing})
                
            except Exception as e:
                logger.warning(f"Error parsing row: {e}")
                continue
        
        return stocks

    _driver = None  # Reusable browser instance
    _driver_lock = None  # Thread lock for browser access
    _max_retries = 3  # Number of retry attempts for browser operations
    
    def _initialize_browser(self):
        """Initialize or reinitialize the browser with optimized settings"""
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        # Close any existing instance first
        if self._driver is not None:
            try:
                self._driver.quit()
            except:
                pass
            self._driver = None
        
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-infobars')
        options.add_argument('--blink-settings=imagesEnabled=false')
        options.add_argument('--js-flags=--expose-gc')
        options.add_argument('--disable-dev-shm-usage')
        
        # Additional memory optimization
        options.add_argument('--disable-browser-side-navigation')
        options.add_argument('--disable-3d-apis')
        options.add_argument('--disable-accelerated-2d-canvas')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=NetworkPrediction,PrefetchDNSOverride')
        options.add_argument('--disable-sync')
        options.add_argument('--mute-audio')
        options.add_argument('--no-first-run')
        options.add_argument('--no-default-browser-check')
        options.add_argument('--memory-model=low')
        options.add_argument('--disable-translate')
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
        
        service = Service(ChromeDriverManager().install())
        self._driver = webdriver.Chrome(service=service, options=options)
        self._driver.set_page_load_timeout(10)  # Even shorter timeout
        
    def check_mc_overestimate(self, ticker: str) -> Dict[str, any]:
        """Get Market Chameleon overestimate data with retry mechanism"""
        import threading
        
        # Initialize thread lock if needed
        if self._driver_lock is None:
            self._driver_lock = threading.Lock()
        
        # Default return values
        default_result = {'win_rate': 0.0, 'quarters': 0}
        
        # Acquire lock for thread safety
        with self._driver_lock:
            # Try to initialize browser if not already running
            if self._driver is None:
                try:
                    self._initialize_browser()
                except Exception as e:
                    logger.error(f"Failed to initialize browser: {e}")
                    return default_result
            
            # Retry loop
            retries = 0
            while retries < self._max_retries:
                try:
                    # Check if browser needs reinitializing
                    try:
                        # Quick test if browser is responsive
                        self._driver.window_handles
                    except:
                        # Browser crashed or not responsive, reinitialize
                        logger.info(f"Browser needs reinitializing for {ticker}")
                        self._initialize_browser()
                    
                    url = f"https://marketchameleon.com/Overview/{ticker}/Earnings/Earnings-Charts/"
                    self._driver.get(url)
                    
                    wait = WebDriverWait(self._driver, 8)  # Even shorter timeout
                    section = wait.until(
                        EC.presence_of_element_located((By.CLASS_NAME, "symbol-section-header-descr"))
                    )
            
                    # Default results
                    win_rate = 0.0
                    quarters = 0
                    
                    # Extract both the percentage and quarters data
                    spans = section.find_elements(By.TAG_NAME, "span")
                    for span in spans:
                        if "overestimated" in span.text:
                            # Extract the percentage
                            try:
                                strong = span.find_element(By.TAG_NAME, "strong")
                                win_rate = float(strong.text.strip('%'))
                                
                                # Extract the quarters by parsing the text after the percentage
                                text = span.text
                                quarters_pattern = r"in the last (\d+) quarters"
                                quarters_match = re.search(quarters_pattern, text)
                                if quarters_match:
                                    quarters = int(quarters_match.group(1))
                            except Exception as inner_e:
                                logger.debug(f"Error extracting data for {ticker}: {inner_e}")
                            break
                    
                    # Success - return the data and break the retry loop
                    return {
                        'win_rate': win_rate,
                        'quarters': quarters
                    }
                    
                except Exception as e:
                    logger.warning(f"Error getting MC data for {ticker} (attempt {retries+1}/{self._max_retries}): {e}")
                    retries += 1
                    
                    # Try to reinitialize browser after each failure
                    try:
                        self._initialize_browser()
                    except:
                        pass
                    
                    # Small delay before retry
                    time.sleep(1)
            
            # If we get here, we've exhausted retries
            logger.error(f"Failed to get MC data for {ticker} after {self._max_retries} attempts")
            return default_result

    def validate_stock(self, stock: Dict) -> Dict:
        ticker = stock['ticker']
        analysis = None
        failed_checks = []
        near_miss_checks = []
        metrics = {}
        
        try:
            yf_ticker = yf.Ticker(ticker, session=session)
            
            # Price check (first and fastest)
            current_price = yf_ticker.history(period='1d')['Close'].iloc[-1]
                
            metrics['price'] = current_price
            if current_price < 1.0:
                return {
                    'pass': False,
                    'near_miss': False,
                    'reason': f"Price ${current_price:.2f} < $1.00",
                    'metrics': {'price': current_price}
                }

            # Options availability and expiration check
            options_dates = yf_ticker.options
            if not options_dates:
                return {
                    'pass': False,
                    'near_miss': False,
                    'reason': "No options available",
                    'metrics': {'price': current_price}
                }

            # Check expiration date
            first_expiry = datetime.strptime(options_dates[0], "%Y-%m-%d").date()
            days_to_expiry = (first_expiry - datetime.now().date()).days
            if days_to_expiry > 9:
                return {
                    'pass': False,
                    'near_miss': False,
                    'reason': f"Next expiration too far: {days_to_expiry} days",
                    'metrics': {'price': current_price, 'days_to_expiry': days_to_expiry}
                }

            # Check open interest
            chain = yf_ticker.option_chain(options_dates[0])
            total_oi = chain.calls['openInterest'].sum() + chain.puts['openInterest'].sum()
            if total_oi < 2000:
                return {
                    'pass': False,
                    'near_miss': False,
                    'reason': f"Insufficient open interest: {total_oi}",
                    'metrics': {'price': current_price, 'open_interest': total_oi}
                }
            
            metrics.update({
                'open_interest': total_oi,
                'days_to_expiry': days_to_expiry
            })
            
            # Mandatory check: core analysis
            analysis = self.analyzer.compute_recommendation(ticker)
                
            if "error" in analysis:
                return {
                    'pass': False,
                    'near_miss': False,
                    'reason': f"Analysis error - {analysis['error']}",
                    'metrics': {}
                }
            
            # Term structure check (immediate exit - this is a hard filter)
            term_slope = analysis.get('term_slope', 0)
            metrics['term_structure'] = term_slope
            if term_slope > -0.004:
                return {
                    'pass': False,
                    'near_miss': False,
                    'reason': f"Term structure {term_slope:.4f} > -0.004",
                    'metrics': metrics
                }
                
            # Check ATM option deltas to ensure they are not too far from 0.5
            # Only perform this check if delta values are available
            call_delta = analysis.get('atm_call_delta')
            put_delta = analysis.get('atm_put_delta')
            
            # Skip this check if either delta is None (not available from Yahoo Finance API)
            if call_delta is not None and put_delta is not None:
                try:
                    # Call delta should be <= 0.57 (not too deep ITM)
                    # Put delta should be >= -0.57 (absolute value <= 0.57)
                    call_delta_float = float(call_delta)
                    put_delta_float = float(put_delta)
                    
                    metrics['atm_call_delta'] = call_delta_float
                    metrics['atm_put_delta'] = put_delta_float
                    
                    if call_delta_float > 0.57 or abs(put_delta_float) > 0.57:
                        return {
                            'pass': False,
                            'near_miss': False,
                            'reason': f"ATM options have delta > 0.57 (call: {call_delta_float:.2f}, put: {put_delta_float:.2f})",
                            'metrics': metrics
                        }
                except (TypeError, ValueError) as e:
                    # Log more details about the error
                    logger.debug(f"Skipping delta check for {ticker}: invalid delta values - {e}. Values: call_delta={call_delta}, put_delta={put_delta}")
            
            # Check for minimum expected move of $0.90
            expected_move_pct = analysis.get('expected_move', 'N/A')
            
            # Log the raw expected move value for debugging
            logger.debug(f"Raw expected move for {ticker}: {expected_move_pct}")
            
            if expected_move_pct != 'N/A':
                # Parse the percentage from the string (e.g., "5.20%")
                try:
                    # Handle both string and numeric formats
                    if isinstance(expected_move_pct, str):
                        move_pct = float(expected_move_pct.strip('%')) / 100
                    else:
                        move_pct = float(expected_move_pct) / 100
                        
                    expected_move_dollars = current_price * move_pct
                    metrics['expected_move_dollars'] = expected_move_dollars
                    metrics['expected_move_pct'] = move_pct * 100
                    
                    logger.debug(f"Calculated expected move for {ticker}: ${expected_move_dollars:.2f} ({move_pct*100:.2f}%)")
                    
                    # Reject if expected move is less than $0.90
                    if expected_move_dollars < 0.9:
                        return {
                            'pass': False,
                            'near_miss': False,
                            'reason': f"Expected move ${expected_move_dollars:.2f} < $0.90",
                            'metrics': metrics
                        }
                except (ValueError, AttributeError, TypeError) as e:
                    logger.warning(f"Could not parse expected move for {ticker}: {expected_move_pct} - Error: {e}")
                    
                    # As a fallback, try to calculate expected move from ATM option premiums
                    try:
                        if 'options_dates' in locals() and len(options_dates) > 0:
                            chain = yf_ticker.option_chain(options_dates[0])
                            calls, puts = chain.calls, chain.puts
                            
                            call_idx = (calls['strike'] - current_price).abs().idxmin()
                            put_idx = (puts['strike'] - current_price).abs().idxmin()
                            
                            call_mid = (calls.loc[call_idx, 'bid'] + calls.loc[call_idx, 'ask']) / 2
                            put_mid = (puts.loc[put_idx, 'bid'] + puts.loc[put_idx, 'ask']) / 2
                            straddle = call_mid + put_mid
                            
                            # Using the straddle price as a direct estimate of expected move in dollars
                            expected_move_dollars = straddle
                            metrics['expected_move_dollars'] = expected_move_dollars
                            metrics['expected_move_pct'] = (expected_move_dollars / current_price) * 100
                            
                            logger.info(f"Using fallback method for expected move on {ticker}: ${expected_move_dollars:.2f} ({metrics['expected_move_pct']:.2f}%)")
                            
                            if expected_move_dollars < 0.9:
                                return {
                                    'pass': False,
                                    'near_miss': False,
                                    'reason': f"Expected move (fallback) ${expected_move_dollars:.2f} < $0.90",
                                    'metrics': metrics
                                }
                    except Exception as e2:
                        logger.warning(f"Fallback expected move calculation also failed for {ticker}: {e2}")
            
            # Non-mandatory checks with near-miss ranges
            # Price check
            current_price = yf_ticker.history(period='1d')['Close'].iloc[-1]
            metrics['price'] = current_price
            if current_price < 5.0:
                failed_checks.append(f"Price ${current_price:.2f} < $5.00")
            elif current_price < 7.0:
                near_miss_checks.append(f"Price ${current_price:.2f} < $7.00")
                
            # Volume check
            avg_volume = yf_ticker.history(period='1mo')['Volume'].mean()
                
            metrics['volume'] = avg_volume
            if avg_volume < 1_000_000:
                failed_checks.append(f"Volume {avg_volume:,.0f} < 1M")
            elif avg_volume < 1_500_000:
                near_miss_checks.append(f"Volume {avg_volume:,.0f} < 1.5M") 
            
            # Market Cap to Float ratio check
            market_cap = yf_ticker.info.get('marketCap', 0)
            float_shares = yf_ticker.info.get('floatShares', 0)
            float_ratio = round(market_cap / 1e9, 2) / round(float_shares / 1e6, 2) if float_shares > 0 else 0
            metrics['float_ratio'] = float_ratio

            if float_ratio > 0.4:
                near_miss_checks.append(f"Float ratio {float_ratio:.2f} > 0.4")

            # Market Chameleon check - only if we haven't failed already
            if not failed_checks:  # Skip if already failing other checks
                mc_data = self.check_mc_overestimate(ticker)
                win_rate = mc_data['win_rate']
                quarters = mc_data['quarters']
                
                # Store both percentage and quarters in metrics
                metrics['win_rate'] = win_rate
                metrics['win_quarters'] = quarters
                
                # Apply the new threshold of 50%
                if win_rate < 50.0:
                    if win_rate >= 40.0:  # Between 40-50% is now a near miss
                        near_miss_checks.append(f"Winrate {win_rate}% < 50% (over {quarters} earnings)")
                    else:  # Below 40% is still a failure
                        failed_checks.append(f"Winrate {win_rate}% < 40% (over {quarters} earnings)")
            else:
                # Add placeholders if we skip
                metrics['win_rate'] = 0.0
                metrics['win_quarters'] = 0
            
            # IV/RV check
            iv_rv_ratio = analysis.get('iv30_rv30', 0)
            metrics['iv_rv_ratio'] = iv_rv_ratio

            # Use dynamic thresholds based on market conditions
            if iv_rv_ratio < self.iv_rv_near_miss_threshold:
                failed_checks.append(f"IV/RV ratio {iv_rv_ratio:.2f} < {self.iv_rv_near_miss_threshold}")
            elif iv_rv_ratio < self.iv_rv_pass_threshold:
                near_miss_checks.append(f"IV/RV ratio {iv_rv_ratio:.2f} < {self.iv_rv_pass_threshold}")

            # Determine final categorization
            
            # Is this a passing stock (original criteria)?
            is_passing = len(failed_checks) == 0 and len(near_miss_checks) == 0
            
            # Is this a near miss with good term structure?
            is_near_miss_good_term = (len(failed_checks) == 0 and 
                                      len(near_miss_checks) > 0 and 
                                      term_slope <= -0.006)
            
            # Assign tiers:
            # - Tier 1: Original "recommended" stocks (passing all criteria)
            # - Tier 2: Near misses with term structure <= -0.006
            # - Near misses: The rest (term structure must still be <= -0.004)
            if is_passing:
                tier = 1
                metrics['tier'] = 1
                is_tier2 = False
                is_near_miss = False
            elif is_near_miss_good_term:
                tier = 2
                metrics['tier'] = 2
                is_tier2 = True
                is_near_miss = False
            else:
                tier = 0
                metrics['tier'] = 0
                is_tier2 = False
                is_near_miss = len(failed_checks) == 0  # Only a near miss if it only fails non-critical checks

            return {
                'pass': is_passing or is_tier2,  # Both Tier 1 and Tier 2 pass
                'tier': tier,
                'near_miss': is_near_miss,
                'reason': " | ".join(failed_checks) if failed_checks else (
                    " | ".join(near_miss_checks) if near_miss_checks else 
                    "Tier 1 Trade" if is_passing else 
                    "Tier 2 Trade" if is_tier2 else 
                    "Near Miss"
                ),
                'metrics': metrics
            }

        except Exception as e:
            logger.warning(f"Error validating {ticker}: {e}")
            return {
                'pass': False,
                'near_miss': False,
                'metrics': {},
                'reason': f"Validation error: {str(e)}"
            }

    def adjust_thresholds_based_on_spy(self):
        """
        Check SPY's current IV/RV ratio and adjust thresholds if market IV is low.
        If SPY IV/RV <= 1.1, reduce thresholds by 0.1.
        """
        try:
            # Calculate SPY's IV/RV
            spy_analysis = self.analyzer.compute_recommendation('SPY')
            if 'error' not in spy_analysis:
                spy_iv_rv = spy_analysis.get('iv30_rv30', 0)
                logger.info(f"Current SPY IV/RV ratio: {spy_iv_rv:.2f}")
                
                # Three-tiered threshold system based on market conditions
                if spy_iv_rv <= 0.75:  # Severe low volatility (new tier)
                    self.iv_rv_pass_threshold = 0.90  # Relaxed by 0.35
                    self.iv_rv_near_miss_threshold = 0.65  # Relaxed by 0.35
                    logger.info(f"Market IV/RV is severely low ({spy_iv_rv:.2f}). Relaxing IV/RV thresholds by 0.35")
                elif spy_iv_rv <= 0.85:  # Extreme low volatility
                    self.iv_rv_pass_threshold = 1.00  # Relaxed by 0.25
                    self.iv_rv_near_miss_threshold = 0.75  # Relaxed by 0.25
                    logger.info(f"Market IV/RV is extremely low ({spy_iv_rv:.2f}). Relaxing IV/RV thresholds by 0.25")
                elif spy_iv_rv <= 1.0:  # Moderately low volatility
                    self.iv_rv_pass_threshold = 1.10  # Relaxed by 0.15
                    self.iv_rv_near_miss_threshold = 0.85  # Relaxed by 0.15
                    logger.info(f"Market IV/RV is low ({spy_iv_rv:.2f}). Relaxing IV/RV thresholds by 0.15")
                else:  # Normal market conditions
                    logger.info(f"Normal market IV/RV ({spy_iv_rv:.2f}). Using standard thresholds")
                
                logger.info(f"Current IV/RV thresholds - Pass: {self.iv_rv_pass_threshold}, Near Miss: {self.iv_rv_near_miss_threshold}")
            else:
                logger.warning(f"Could not calculate SPY IV/RV: {spy_analysis.get('error')}")
                logger.info(f"Using standard IV/RV thresholds - Pass: {self.iv_rv_pass_threshold}, Near Miss: {self.iv_rv_near_miss_threshold}")
        except Exception as e:
            logger.warning(f"Error calculating SPY IV/RV: {e}")
            logger.info(f"Using standard IV/RV thresholds - Pass: {self.iv_rv_pass_threshold}, Near Miss: {self.iv_rv_near_miss_threshold}")
            
    def analyze_ticker(self, ticker: str) -> Dict:
        """
        Analyze a specific ticker symbol and return detailed results regardless of pass/fail status.
        
        Args:
            ticker: The ticker symbol to analyze (e.g., 'AAPL', 'MSFT')
            
        Returns:
            Dictionary containing all metrics and validation results
        """
        try:
            # Create a stock dict as expected by validate_stock
            stock = {'ticker': ticker, 'timing': 'Manual Check'}
            
            # Adjust thresholds based on market conditions
            self.adjust_thresholds_based_on_spy()
            
            # Run all validation checks on this stock
            result = self.validate_stock(stock)
            
            # Get all available metrics
            metrics = result.get('metrics', {}) if 'metrics' in result else {}
            
            # Add pass/fail status to the metrics
            metrics['pass'] = result.get('pass', False)
            metrics['near_miss'] = result.get('near_miss', False) 
            metrics['tier'] = result.get('tier', 0) if 'tier' in result else 0
            metrics['reason'] = result.get('reason', "Unknown status")
            
            # Add current thresholds used for context
            metrics['iv_rv_pass_threshold'] = self.iv_rv_pass_threshold
            metrics['iv_rv_near_miss_threshold'] = self.iv_rv_near_miss_threshold
            
            # Add SPY IV/RV info
            try:
                spy_analysis = self.analyzer.compute_recommendation('SPY')
                if 'error' not in spy_analysis:
                    metrics['spy_iv_rv'] = spy_analysis.get('iv30_rv30', 0)
            except:
                metrics['spy_iv_rv'] = 'N/A'
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error analyzing ticker {ticker}: {e}")
            return {
                'error': str(e),
                'pass': False,
                'near_miss': False,
                'reason': f"Analysis error: {str(e)}"
            }
            
    def scan_earnings(self, input_date: Optional[str] = None, workers: int = 0, use_finnhub: bool = False, 
                    use_dolthub: bool = False, all_sources: bool = False) -> Tuple[List[str], List[Tuple[str, str]], Dict[str, Dict]]:
        """Main entry point for scanning earnings with enhanced error handling to prevent crashes"""
        
        # Store these parameters as instance variables for use throughout the class
        self.current_input_date = input_date
        self.use_finnhub = use_finnhub
        self.use_dolthub = use_dolthub
        self.all_sources = all_sources
        
        # Start with empty results in case of early errors
        recommended = []
        near_misses = []
        stock_metrics = {}
        
        try:
            # Adjust IV/RV thresholds based on market conditions
            self.adjust_thresholds_based_on_spy()
            
            # Get scan dates with error handling
            try:
                post_date, pre_date = self.get_scan_dates(input_date)
            except Exception as e:
                logger.error(f"Error getting scan dates: {e}")
                return recommended, near_misses, stock_metrics
            
            # Fetch earnings data in parallel with timeout and error handling
            post_stocks = []
            pre_stocks = []
            
            try:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    post_future = executor.submit(self.fetch_earnings_data, post_date)
                    pre_future = executor.submit(self.fetch_earnings_data, pre_date)
                    
                    # Get results with timeout to prevent hanging
                    try:
                        post_stocks = post_future.result(timeout=30)  # 30 second timeout
                    except Exception as e:
                        logger.error(f"Error fetching post-market earnings: {e}")
                        post_stocks = []
                        
                    try:
                        pre_stocks = pre_future.result(timeout=30)  # 30 second timeout
                    except Exception as e:
                        logger.error(f"Error fetching pre-market earnings: {e}")
                        pre_stocks = []
            except Exception as e:
                logger.error(f"Error in parallel processing of earnings data: {e}")
                # Initialize with empty lists in case of errors
                post_stocks = []
                pre_stocks = []
        except Exception as e:
            logger.error(f"Error adjusting thresholds or fetching earnings data: {e}")
            return recommended, near_misses, stock_metrics
            
        # Initialize candidates list properly - outside of the try block
        candidates = []
        # Filter candidates (using list comprehensions for speed)
        candidates = [s for s in post_stocks if s['timing'] == 'Post Market'] + \
                     [s for s in pre_stocks if s['timing'] == 'Pre Market']
        
        logger.info(f"Found {len(candidates)} initial candidates")
        
        recommended = []
        near_misses = []
        stock_metrics = {}
        
        # Process in parallel if workers specified
        if workers > 0:
            # Limit max workers for stability (especially with browser operations)
            effective_workers = min(workers, 8)  # Cap at 8 workers max for stability
            logger.info(f"Using parallel processing with {effective_workers} workers")
            
            with ThreadPoolExecutor(max_workers=effective_workers) as executor:
                # Submit all stocks for processing
                futures = [executor.submit(self.validate_stock, stock) for stock in candidates]
                
                # Process results as they complete
                with tqdm(total=len(candidates), desc="Analyzing stocks") as pbar:
                    for i, future in enumerate(futures):
                        stock = candidates[i]
                        ticker = stock['ticker']
                        try:
                            result = future.result(timeout=60)  # Add timeout to prevent hanging threads
                            
                            if result['pass']:
                                recommended.append(ticker)
                                stock_metrics[ticker] = result['metrics']
                            elif result['near_miss']:
                                near_misses.append((ticker, result['reason']))
                                stock_metrics[ticker] = result['metrics']
                        except Exception as e:
                            logger.error(f"Error processing {ticker}: {e}")
                        finally:
                            pbar.update(1)
        else:
            # Original batched sequential processing
            batches = [candidates[i:i+self.batch_size] 
                      for i in range(0, len(candidates), self.batch_size)]
            
            with tqdm(total=len(candidates), desc="Analyzing stocks") as pbar:
                for batch in batches:
                    for stock in batch:
                        result = self.validate_stock(stock)
                        ticker = stock['ticker']
                        
                        if result['pass']:
                            recommended.append(ticker)
                            stock_metrics[ticker] = result['metrics']
                        elif result['near_miss']:
                            near_misses.append((ticker, result['reason']))
                            stock_metrics[ticker] = result['metrics']
                        pbar.update(1)
                    
                    if batch != batches[-1]:
                        time.sleep(5)  # Reduced sleep time
        
        return recommended, near_misses, stock_metrics