from multiprocessing import Pool, Value, Lock
import sys
from time import sleep

# Set a smaller number for a demo
grid = [[i, j] for i in range(100) for j in range(100)]

# Initialize a shared counter and a lock
counter = Value('i', 0)
lock = Lock()

# This function will be executed by each worker process
def run(params):
    # Perform some computation
    a = 2**32 / 65537
    sleep(.1)  # Simulate a task taking some time

    # Update the shared counter
    with lock:
        counter.value += 1

    return (params, a)

if __name__ == '__main__':
    result_list = []

    with Pool() as pool:
        # Submit all tasks and store AsyncResult objects
        async_results = [pool.apply_async(run, args=(params,)) for params in grid]

        # Periodically check progress and update the progress counter
        while True:
            completed = sum(1 for res in async_results if res.ready())
            progress = completed / len(grid) * 100
            sys.stdout.write(f'\rCompleted tasks: {progress:.2f}%')
            sys.stdout.flush()

            if completed == len(grid):
                break
            sleep(0.5)  # Update every half second

        # Close the pool and wait for the tasks to complete
        pool.close()
        pool.join()

        # Collect results from the AsyncResult objects
        for async_result in async_results:
            result_list.append(async_result.get())

    print("\nAll tasks completed.")
    # Print or process the results
    print(result_list)
