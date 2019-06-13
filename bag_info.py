#! /usr/bin/python3

import rosbag
from  anytree import Node, RenderTree
import texttable
import re

def extract_topics(bag_file):
	return bag_file.get_type_and_topic_info().topics

def extract_frames(bag_file):
	first_message = True
	begin_time = 0
	frames_list = {}
	frames_roots = []
	for topic, msg, t in bag_file.read_messages(topics=["/tf"]):
		if first_message == True:
			begin_time = t.secs
			first_message = False
		if abs(t.secs - begin_time) > 2:
			break
		for transform in msg.transforms:
			if transform.header.frame_id not in frames_list:
				frames_list[transform.header.frame_id] = Node(transform.header.frame_id)
			if transform.child_frame_id not in frames_list:
				frames_list[transform.child_frame_id] = Node(transform.child_frame_id,
				                                             parent=frames_list[transform.header.frame_id])
			
			else:
				frames_list[transform.child_frame_id].parent=frames_list[transform.header.frame_id]
	for node_name, node in frames_list.items():
		if node.root not in frames_roots:
			frames_roots.append(node.root)
	return frames_roots

def find_frame(node,frame,node_list):
	if frame in node.name:
		node_list.append(node)
	for child in node.children:
		find_frame(child,frame,node_list)
			

def extract_parrent_and_child_frames(frame_roots,parent_frames,child_frames):
	d = {}
	for root in frame_roots:		
		for possible_world_frame in parent_frames:
			world_frames = []
			find_frame(root,possible_world_frame,world_frames)
			for world_frame in world_frames:
				if world_frame not in d:
					d[world_frame] = []
				for possible_child_frame in child_frames:
					current_frames = []
					find_frame(world_frame,possible_child_frame,current_frames)
					for current_frame in current_frames:
						if current_frame not in d[world_frame]:
							d[world_frame].append(current_frame)
	return d

#bag=rosbag.Bag("/home/user/data/2011-01-25-06-29-26.bag")
#bag=rosbag.Bag("/home/user/data/2011-01-27-07-49-54.bag")
#bag=rosbag.Bag("/home/user/data/2011-04-11-07-34-27.bag")
bag=rosbag.Bag("/home/user/data/rgbd_dataset_freiburg2_pioneer_360.bag")
topics = extract_topics(bag)
#################################### print topics #############################################           
tab = texttable.Texttable()                                                                   #
tab.header(["topic name","msgs type","msgs count","connections","frequency"])                 #
for topic, info in topics.items():                                                            #
	tab.add_row((topic,info.msg_type,info.message_count,info.connections,info.frequency)) #
print(tab.draw())                                                                             #
###############################################################################################

frames_roots = extract_frames(bag)
################### print tf frames ##############
for root in frames_roots:                        #
	for pre, fill, node in RenderTree(root): #
		print("%s%s" % (pre,node.name))  #
##################################################

laser_frames = extract_parrent_and_child_frames(frames_roots,["world","odom"],["laser","robot","base"])
camera_frames = extract_parrent_and_child_frames(frames_roots,["world","odom"],["cam","stereo","robot","base"])

laser_costs = {"laser":1,"robot":0.5,"base":0.5}
camera_costs = {"cam":2,"stereo":1,"robot":0.5,"base":0.5}

print("laser frames:")
for k,vs in laser_frames.items():
	for v in vs:
		total_cost = 0
		for sensor, cost in laser_costs.items():
			if sensor in v.name:
				total_cost += cost
		print(k.name,"->",v.name,total_cost)
print("camera frames:")
for k,vs in camera_frames.items():
	for v in vs:
		total_cost = 0
		for sensor, cost in camera_costs.items():
			if sensor in v.name:
				total_cost += cost
		print(k.name,"->",v.name,total_cost)

