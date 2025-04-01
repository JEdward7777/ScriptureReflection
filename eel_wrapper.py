
import streamlit.web.bootstrap as bootstrap
from streamlit import config
import threading
import time
import eel

def launch_browser():
    #time.sleep(2)

    for mode, browser_module in eel.browsers._browser_modules.items():
        path = eel.browsers._browser_paths.get(mode)
        if path is None:
            # Don't know this browser's path, try and find it ourselves
            path = browser_module.find_path()
            eel.browsers._browser_paths[mode] = path

        if path:
            eel.browsers.open(start_pages=[""], options={
                'host': 'localhost',
                'port': 8501,
                'mode': mode,
                'cmdline_args': [],
                'app_mode': True } )
            break

    print("Browser opened")



def run_streamlit():
    # Set the default port if needed
    config.set_option("server.port", 8501)
    config.set_option("server.headless", True)
    
    # Run Streamlit app
    bootstrap.run("streamlit_reflector.py", args=[], flag_options={}, is_hello=False)



def main():
    launch_browser()
    run_streamlit()

if __name__ == "__main__":
    main()