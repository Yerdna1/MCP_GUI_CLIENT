import asyncio
import logging
import threading
import traceback

def run_async(async_func, timeout=30):
    """
    Runs async code in a new thread with a dedicated event loop and timeout.
    Moved from MCPConnectionManager.
    """
    result = None
    exception = None
    thread_done = threading.Event()

    def thread_func():
        nonlocal result, exception
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def run_with_timeout():
                return await asyncio.wait_for(async_func(), timeout)
            result = loop.run_until_complete(run_with_timeout())
        except asyncio.TimeoutError:
            exception = TimeoutError(f"Operation timed out after {timeout} seconds")
            logging.error(f"MCP operation timed out after {timeout} seconds")
        except Exception as e:
            exception = e
            logging.error(f"Error in async operation: {str(e)}")
            logging.debug(traceback.format_exc())
        finally:
            # Refined cleanup: Cancel pending tasks and wait briefly
            try:
                current_task = asyncio.current_task(loop)
                tasks = [task for task in asyncio.all_tasks(loop) if task is not current_task]
                if tasks:
                    logging.debug(f"Attempting to cancel {len(tasks)} pending tasks...")
                    for task in tasks:
                        task.cancel()
                    # Wait briefly for cancellations to finish
                    loop.run_until_complete(asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5.0))
                    logging.debug("Finished gathering cancelled tasks.")
            except asyncio.TimeoutError:
                 logging.warning("Timed out waiting for cancelled tasks to finish during cleanup.")
            except Exception as e:
                logging.error(f"Error cancelling/gathering pending tasks during cleanup: {str(e)}")
            finally:
                # Proceed with closing the loop
                try:
                    # Ensure loop is stopped before closing
                    if loop.is_running():
                        loop.stop()
                    if not loop.is_closed():
                        loop.close()
                        logging.debug("Event loop closed.")
                    else:
                        logging.debug("Event loop already closed.")
                except Exception as e:
                     logging.error(f"Error closing event loop: {str(e)}")
                finally:
                     # Signal completion regardless of cleanup success/failure
                     logging.debug("Signalling thread completion.")
                     thread_done.set()

    thread = threading.Thread(target=thread_func)
    thread.daemon = True
    thread.start()

    thread_timeout = timeout + 30
    if not thread_done.wait(thread_timeout):
        logging.error(f"Thread execution exceeded timeout ({thread_timeout}s)")
        exception = TimeoutError(f"Thread execution exceeded timeout ({thread_timeout}s)")

    if exception:
        logging.error(f"Async operation failed with: {exception}")
        raise exception

    return result
