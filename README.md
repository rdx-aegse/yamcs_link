# yamcs_link

Python library to facilitate creating applications interacting with a YAMCS server. 

Example:
```
class MyEnum(Enum):
    VALUE1=1
    VALUE2=2

class MyComponent(YAMCSObject):
    def __init__(self, name):
        YAMCSObject.__init__(self, name)

    @telemetry(1)
    def my_telemetry1(self) -> MyEnum:
        return MyEnum.VALUE1.value

    @telemetry(2)
    def my_telemetry2(self) -> U8:
        return 42

    @telecommand
    def my_command(self, arg1: U16, arg2: F32) -> U8:
        logging.info(f'MyComponent.my_command was invoked on {self.yamcs_name} with args {arg1}, {arg2}')
        return 0

yamcs_link = YAMCS_link("my_link", tcp_port=YAMCS_TC_PORT, udp_port=YAMCS_TM_PORT) 
my_component = MyComponent("component1")
yamcs_link.register_yamcs_child(my_component)

yamcs_link.generate_mdb(DIR_MDB_OUT, MDB_NAME, VERSION) 
#If for some reason you do not generate_mdb, do call update_index() before service()

# Main loop
try:
    while True:
        #Possible to do things here if your app doesn't inherit from YAMCS_link
        yamcs_link.service() #Run TM sending and TC handling
        time.sleep(0.1) #Small delay to prevent busy-waiting
except KeyboardInterrupt:
    logging.info("Exiting main loop.")
finally:
    yamcs_link.shutdown() 
```

YAMCS_link runs the application, and any object inheriting from either YAMCSObject or YAMCSContainer can be registered in the link to attach its method tagged with the @telemetry or @telecommand decorators. Use YAMCSContainers if your application has hierarchical components that should be reflected in YAMCS, YAMCSObjects everywhere else. As long as the register_yamcs_child() chain is not broken between YAMCS_link and your component, it will be connected to YAMCS. 

Events are the natural next improvement which will be added later on. 

## Getting started
 
- To develop a new application, using the files from yamcs_link/src standalone is the least involved way to get started. There are no dependencies required (tested with python 3.14), and yamcs_link.py contains an example of main program if run directly. However, a properly configured YAMCS instance will be needed for the script to succeed.
- To test the demonstration script in yamcs_link.py, simply run run.sh at the root of the repository. [docker](https://docs.docker.com/engine/install) and [docker compose](https://docs.docker.com/compose/install/linux/#install-using-the-repository) are required. A YAMCS instance will be deployed, with which it will be possible to interact from any browser at 127.0.0.1:8090. YAMCS Studio can also be used instead of the web client. 

## Notes

Note that the YAMCS mission databases are generated as CSV files, which are then compiled into a single XLS by the yamcs_server application. The server application waits for the CSV files to appear in their dedicated folder (in a shared volume between both containers), then proceeds to launching YAMCS. 