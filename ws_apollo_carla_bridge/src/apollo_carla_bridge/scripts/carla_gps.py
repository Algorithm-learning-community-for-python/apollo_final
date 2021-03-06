#!/usr/bin/env python

import rospy
from modules.localization.proto.imu_pb2 import CorrectedImu
from modules.localization.proto.gps_pb2 import Gps
from modules.localization.proto.pose_pb2 import Pose
from pb_msgs.msg import Quaternion
from pb_msgs.msg import Chassis
from pb_msgs.msg import GnssStatus
from pb_msgs.msg import InsStatus
from pb_msgs.msg import GnssBestPose
from std_msgs.msg import String

from math import radians, degrees
from math import cos
from math import sin

import tf

import chassis_faker

APOLLO_GPS_TOPIC = '/apollo/sensor/gnss/odometry'
APOLLO_CORRECTED_IMU_TOPIC = '/apollo/sensor/gnss/corrected_imu'
APOLLO_GPS_STATUS_TOPIC = '/apollo/sensor/gnss/gnss_status'
APOLLO_INS_STATUS_TOPIC = '/apollo/sensor/gnss/ins_status'
APOLLO_GPS_BESTPOSE_TOPIC = '/apollo/sensor/gnss/best_pose'

CARLA_PLAYER_VEHICLE_TOPIC = '/player_vehicle'

def euler_from_quarterion(x, y, z, w):
    """
    Convert quarterion into euler angles

    :param x,y,z,w: quaterion
    :type x,y,z,w: quaterion
    :return: euler angles (roll, pitch, yaw)
    """
    import math
    t0 = +2.0 * (w * x + y * z)
    t1 = +1.0 - 2.0 * (x * x + y * y)
    X = math.degrees(math.atan2(t0, t1))

    t2 = +2.0 * (w * y - z * x)
    t2 = +1.0 if t2 > +1.0 else t2
    t2 = -1.0 if t2 < -1.0 else t2
    Y = math.degrees(math.asin(t2))

    t3 = +2.0 * (w * z + x * y)
    t4 = +1.0 - 2.0 * (y * y + z * z)
    Z = math.degrees(math.atan2(t3, t4))

    return X, Y, Z

def forward_gps(data, pubs):
    """
    Forward the GPS data from carla to apollo

    :param data: player_vehicle topic input
    :type data: string
    :param pubs: publishers to foreward the information
    :type pubs: rospy.Publisher
    """
    pub_gps = pubs[0]
    pub_corrected_imu = pubs[1]
    pub_gps_status = pubs[2]
    pub_ins_status = pubs[3]
    pub_gps_bestpose = pubs[4]
    chassis = pubs[5]

    ''' 
        [0] location.x
        [1] location.y
        [2] location.z
        [3] rotation.roll
        [4] rotation.pitch
        [5] rotation.yaw
        [6] rotation.w
        [7] angular_velocity.x
        [8] angular_velocity.y
        [9] angular_velocity.z
        [10] linear_velocity.x
        [11] linear_velocity.y
        [12] linear_velocity.z
        [13] acceleration.x
        [14] acceleration.y
        [15] acceleration.z
        [16] forward_speed
    '''
    arr = data.data.split()

    qx = float(arr[3])
    qy = float(arr[4])
    qz = float(arr[5])
    qw = float(arr[6])

    #calculating euler angles form quarterion to subtract 90 degree from yaw 
    # -> heading in apollo is 0 when facing east while heading in carla is 0 when facing north
    roll, pitch, yaw = euler_from_quarterion(qx, qy, qz, qw)
    yaw = yaw - 90
    qq = tf.transformations.quaternion_from_euler(radians(roll), radians(pitch), radians(yaw))
    p = Pose()
    # needed for localization
    q = Quaternion()
    q.qx = qq[0]
    q.qy = qq[1]
    q.qz = qq[2]
    q.qw = qq[3]
    p.position.x = float(arr[0])
    #add 182.5 to y 
    p.position.y = float(arr[1]) + 182.5 
    p.position.z = float(arr[2])

    p.orientation.qx = q.qx
    p.orientation.qy = q.qy
    p.orientation.qz = q.qz
    p.orientation.qw = q.qw

    # needed for routing
    p.angular_velocity_vrf.x = float(arr[7])
    p.angular_velocity_vrf.y = float(arr[8])
    p.angular_velocity_vrf.z = float(arr[9])
    p.angular_velocity.x = float(arr[7])
    p.angular_velocity.y = float(arr[8])
    p.angular_velocity.z = float(arr[9])
    p.linear_acceleration.x = float(arr[13])
    p.linear_acceleration.y = float(arr[14])
    p.linear_acceleration.z = float(arr[15])
    p.linear_acceleration_vrf.x = float(arr[13])
    p.linear_acceleration_vrf.y = float(arr[14])
    p.linear_acceleration_vrf.z = float(arr[15])

    # needed for prediction
    p.linear_velocity.x = float(arr[10])
    p.linear_velocity.y = float(arr[11])
    p.linear_velocity.z = float(arr[12])

    msg_gps = Gps()
    msg_gps.header.timestamp_sec = float(arr[17])
    msg_gps.localization.CopyFrom(p)

    msg_corrected_imu = CorrectedImu()
    msg_corrected_imu.header.timestamp_sec = float(arr[17])
    msg_corrected_imu.imu.CopyFrom(p)

    pub_corrected_imu.publish(msg_corrected_imu)
    pub_gps.publish(msg_gps)

    gnss_stat = GnssStatus()
    gnss_stat.solution_completed = True
    pub_gps_status.publish(gnss_stat)

    ins_stat = InsStatus()
    ins_stat.type = 2
    pub_ins_status.publish(ins_stat)

    gnss_bestpose = GnssBestPose()
    gnss_bestpose.measurement_time = 3
    pub_gps_bestpose.publish(gnss_bestpose)

    chassis[1].speed_mps = float(arr[16])
    chassis[1].gear_location = 1

    chassis[0].publish(chassis[1])

def setup():
    """
    Setup publishers and subscribers

    """

    pub_gps = rospy.Publisher(APOLLO_GPS_TOPIC, Gps, queue_size=1)
    pub_corrected_imu = rospy.Publisher(APOLLO_CORRECTED_IMU_TOPIC, CorrectedImu, queue_size=1)
    pub_gps_status = rospy.Publisher(APOLLO_GPS_STATUS_TOPIC, GnssStatus, queue_size=1)
    pub_ins_status = rospy.Publisher(APOLLO_INS_STATUS_TOPIC, InsStatus, queue_size=1)
    pub_gps_bestpose = rospy.Publisher(APOLLO_GPS_BESTPOSE_TOPIC, GnssBestPose, queue_size=1)
    rospy.Subscriber(CARLA_PLAYER_VEHICLE_TOPIC, String, forward_gps, [pub_gps, pub_corrected_imu, pub_gps_status, pub_ins_status, pub_gps_bestpose, chassis_faker.setup()], queue_size=1)

def main():
    """
    Initialize gps_faker node and run setup

    """
    rospy.init_node('gps_faker')
    setup()
    rospy.spin()

if __name__ == '__main__':
    main()
