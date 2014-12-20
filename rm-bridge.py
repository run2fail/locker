import pyroute2

ip = pyroute2.IPDB()
try:
    with ip.interfaces['locker_simple'] as i:
        i.remove()
finally:
    ip.release()

