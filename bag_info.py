#! /usr/bin/python3

import rosbag
#import texttable
import json
import sys
import os
from difflib import SequenceMatcher
import rospy
import random

def extract_topics(bag_file):
	return bag_file.get_type_and_topic_info().topics

def tree_frames(bag_file):
	first_message = True # variables to cut first secs of bag
	begin_time = 0       #

	frames_list = {}  # output variables: {frame:[child1, child2], child1:[child_child]...}
	frames_roots = [] #

	# go for all messages in tf
	for topic, msg, t in bag_file.read_messages(topics=["/tf","tf"]):
		# cut first seconds
		if first_message == True:
			begin_time = t.secs
			first_message = False
		if abs(t.secs - begin_time) > 2:
			break

		# go for all transforms
		for transform in msg.transforms:
			parent = transform.header.frame_id
			child = transform.child_frame_id

			if parent not in frames_list:
				frames_list[parent] = []
				frames_roots.append(parent)
			if child not in frames_list[parent]:
				frames_list[parent].append(child)
			if child not in frames_list:
				frames_list[child] = []
			if child in frames_roots:
				frames_roots.remove(child)
	return frames_list,frames_roots

def find_frame(frame_dict,frame_root,name,out_frames_list):
	if name in frame_root:
		out_frames_list.append(frame_root)
	for child in frame_dict[frame_root]:
		find_frame(frame_dict,child,name,out_frames_list)
			

def extract_parrent_and_child_frames(frame_dict, frame_roots, wanted_parent_frames, wanted_child_frames, unwanted_child_frames=[]):
	d = {}
	unwanted_child_frames.append("hack") #should be here
	for root in frame_roots:		
		for wanted_world_frame in wanted_parent_frames:
			world_frames = []
			find_frame(frame_dict,root,wanted_world_frame,world_frames)
			for world_frame in world_frames:
				if world_frame not in d:
					d[world_frame] = []
				for wanted_child_frame in wanted_child_frames:
					current_frames = []
					find_frame(frame_dict,world_frame,wanted_child_frame,current_frames)
					for current_frame in current_frames:
						for unwanted_child_frame in unwanted_child_frames:
							if unwanted_child_frame not in current_frame:
								if current_frame not in d[world_frame]:
									d[world_frame].append(current_frame)
	return d

def print_tree_recursive(d,name,height):
	print("    "*height+name)
	for child in d[name]:
		print_tree_recursive(d,child,height+1)
def print_tree(d,roots):
	for root in roots:
		print_tree_recursive(d,root,0)


def range_by_cost(parents_children_dict,frames_and_costs):
	out_d = []
	for parent, children in parents_children_dict.items():
		for child in children:
			total_cost = 0
			for frame_name, cost in frames_and_costs.items():
				if frame_name in parent or frame_name in child:
					total_cost += cost
			out_d.append((parent,child,total_cost))
	out_d.sort(key = lambda x: x[2],reverse = True)
	return [[elem[0], elem[1]] for elem in out_d]
	
def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def extract_tf_frame(bag_file,topic):
	topic_frame = {}
	for t, msg, time in bag_file.read_messages(topics=[topic]):
		try:
			topic_frame = msg.header.frame_id
		except AttributeError:
			topic_frame = ""
		break
	return topic_frame

def match_topic_types(bag):
	topicmatches = {'camera':[], 
	                'camera_left':[],
	                'camera_right':[],
	                'camera_depth':[],
	                'laser_scan':[],
	                'imu':[],
	                'odometry':[]} # to hold topics with matching message types

	# dictionary of score weights
	# structure {sensor:(message_type, [(keyword, weight), (keyword, weight)])}
	topictypes = {'camera':('sensor_msgs/Image', [('0',1), ('stereo',1),('cam',2)]), 
	              'camera_left':('sensor_msgs/Image', [('left',5), ('_l_',1),('cam',2)]), 
	              'camera_right':('sensor_msgs/Image',[('right',5), ('_r_',1),('cam',2)]), 
	              'camera_depth':('sensor_msgs/Image',[('depth',5), ('_d_',1),('cam',2)]), 
	              'laser_scan':('sensor_msgs/LaserScan', [('base',1), ('scan',2), ('laser', 1), ('robot', 1)]), 
	              'imu':('sensor_msgs/Imu',[('0',1)]), 
	              'odometry':('nav_msgs/Odometry',[('',1)])} 
	cam_topics = [] # to hold cameras
	cam_info_topics = [] # to hold CameraInfo topics

	topics = extract_topics(bag)
	items = topics.items()

	for topic, info in items: # loop over topics
		for match in topicmatches:
			if info.msg_type in topictypes[match][0]: # if topic has correct message type
				topicmatches[match].append(topic) # append it to matches
			if info.msg_type == 'sensor_msgs/Image': # add cameras and cameraInfo
				cam_topics.append(topic)
			elif info.msg_type == 'sensor_msgs/CameraInfo':
				cam_info_topics.append(topic)

	topicscores = {'camera':[],
	               'camera_left':[],
	               'camera_right':[],
	               'camera_depth':[],
	               'laser_scan':[],
	               'imu':[],
	               'odometry':[]} # to hold scores
	
	for score in topicscores: # loop over scores
		n = len(topicmatches[score])
		topicscores[score] = [0] * n
		s = sum([j[1] for j in topictypes[score][1]])
		for i in range(len(topicmatches[score])):
			for m in topictypes[score][1]: # add some to score if there's a keyword match
				if m[0] in topicmatches[score][i]:
					if m[0] != '':
						topicscores[score][i] += 1.0/s * m[1]

	#print(topicscores) # positive scores

	for score in topicscores: # loop over scores
		for i in range(len(topicscores[score])):
			s = topicscores[score][i]
			t = topicmatches[score][i]

			for topic in topicmatches: # check to see if another sensor has higher score for this topic
				if score == topic: continue
				if t in topicmatches[topic]:
					oidx = topicmatches[topic].index(t)
					if topicscores[topic][oidx] > s:
						topicscores[score][i] -= 1 # if so, subtract from score
						break

	#print(topicscores) # includes positive and negative scores

	assignment = {'camera':[],
	              'camera_left':[],
	              'camera_right':[],
	              'camera_depth':[],
	              'laser_scan':[],
	              'imu':[],
	              'odometry':[]} # final assignment
	for score in topicscores: # assign topics
		scores = [(topicscores[score][i], i) for i in range(len(topicscores[score]))]
		scores_sorted = sorted(scores, reverse=True)
		for s in scores_sorted:
			idx = s[1]
			if ((score != 'camera_depth' or ('depth' in topicmatches[score][idx])) and
				(score != 'camera_right' or ('left' not in topicmatches[score][idx])) and
				(score != 'camera_left' or ('right' not in topicmatches[score][idx]))): # don't add for depth camera unless 'depth' in name
				assignment[score].append(topicmatches[score][idx]) # can alternatively recalculate positive score and check if above threshold

	info_assignment = {}

	# so far observed that CameraInfo topic names are very similar to corresponding image names
	# except they may contain the word 'info' somewhere, so for every topic with type CameraInfo, can
	# find the most similar topic name with type Image using Python built-in function (from difflib)
	for info in cam_info_topics:
		best = (0,0)
		for i in range(len(cam_topics)): # find the most similar topic name with type sensor_msgs/Image
			sim = similar(info.lower(), cam_topics[i].lower())
			if sim > best[0]:
				best = (sim, i)
		info_assignment[info] = cam_topics[best[1]] # make assignment

	assignment['camera_intrinsics'] = {}
	for info in info_assignment: # call get_camera_info and append results to final assignment
		assignment['camera_intrinsics'][info_assignment[info]] = get_camera_info(bag, info, info_assignment[info])

	return assignment

def get_camera_info(bag, topic, cam): # returns a dictionary of message attributes for topics with type CameraInfo
	def str_to_dict(lines): # helper: turn a list of words separated by a colon into a dictionary
		dct = {}
		for line in lines: # loop over lines
			split = line.split(':', 1) # split by the first colon
			if split[1].strip() != '' and split[0][0] != ' ':
				dct[split[0].strip()] = eval(split[1].strip()) # evaluate string and add to dictionary
		return dct

	def frame_rate2(tpc, samples=15, size=2, max_tries=50):
		rates = []
		while samples > 0:
			if max_tries < 1 or samples < 1:
				break
			max_tries -= 1
			start = random.randint(int(bag.get_start_time() * 1000), int(bag.get_end_time() * 1000))
			try:
				msg_gen = bag.read_messages(topics = tpc, start_time=rospy.Time.from_sec(start/1000))
				frames = [msg_gen.next()[1].header.stamp.to_sec(), msg_gen.next()[1].header.stamp.to_sec()] # may generate StopIteration error
				rates.append((size-1)/(frames[-1] - frames[0])) # divide by zero error
				samples -= 1
			except:
				continue

		rates.sort()
		return 0 if len(rates) < 1 else sum(rates)/len(rates)

	cam_info = {}
	midtime = (bag.get_start_time() + bag.get_end_time()) / 2.0
	for tp, msg, t in bag.read_messages(topics=[topic], start_time=rospy.Time.from_sec(midtime)): # loop over messages (will read only one message)
		text = str(msg)
		lines = text.split('\n')
		cam_info = str_to_dict(lines[6:15]) # turn lines 6-14 of str(msg) into dictionary
		cam_info['roi'] = str_to_dict((str(msg.roi)).split('\n')) # add dictionary properties to cam_info
		#cam_info['header'] = str_to_dict((str(msg.header)).split('\n'))
		#cam_info['header']['stamp'] = {'secs':msg.header.stamp.secs, 'nsecs':msg.header.stamp.nsecs}
		#print('***', cam)
		cam_info['frame_rate'] = int(round(frame_rate2([cam])))
		return cam_info

def match_tf_types(bag, assignments):
	def find_possible_tf_frames_for_topic(bag, frames_dict, frames_roots,
	                                      assignments, assignments_item, assignments_tf_item,
	                                      wanted_world_frames, wanted_child_frames, unwanted_child_frames = ["hack"], #hack should be here
	                                      frames_costs = {}):
		tf_list = []
		assignments[assignments_tf_item] = {}
		for topic in assignments[assignments_item]:
			tf_frame = extract_tf_frame(bag, topic)
			if tf_frame == "":
				frames = extract_parrent_and_child_frames(frames_dict, frames_roots, wanted_world_frames, wanted_child_frames, unwanted_child_frames)
			else:
				frames = extract_parrent_and_child_frames(frames_dict, frames_roots, wanted_world_frames, [tf_frame])
			assignments[assignments_tf_item][topic] = range_by_cost(frames, frames_costs)

	frames_dict,frames_roots = tree_frames(bag)
	# print_tree(frames_dict,frames_roots) #
	
	find_possible_tf_frames_for_topic(bag, frames_dict, frames_roots, assignments, "laser_scan", "laser_tf",
                                          wanted_world_frames = ["world","odom"],wanted_child_frames = ["laser","robot","base"],
	                                  frames_costs = {"world":1, "odom":1, "laser":1, "robot":0.5, "base":0.5})
	find_possible_tf_frames_for_topic(bag, frames_dict, frames_roots, assignments, "camera", "camera_tf",
                                          wanted_world_frames = ["world","odom"], wanted_child_frames = ["rgb","cam","stereo","robot","base"], 
	                                  unwanted_child_frames = ["depth","wheel"],
	                                  frames_costs = {"rgb":1,"world":1, "odom":0.5, "cam":2, "stereo":1, "robot":0.5, "base":0.5,"left":-1,"right":-1,"_l_":-1,"_r_":-1,"/l_":-1,"/r_":-1,"_l/":-1,"_r/":-1,"double":2,"pair":2})
	find_possible_tf_frames_for_topic(bag, frames_dict, frames_roots, assignments, "camera_left", "camera_left_tf",
                                          wanted_world_frames = ["world","odom"], wanted_child_frames = ["rgb","left_camera","left","l_c","_l/","/l_","_l_","cam","stereo"], 
	                                  unwanted_child_frames = ["robot","base","wheel","finger","depth","_d_","right","_r_","/r_","_r/"],
	                                  frames_costs = {"rgb":1,"left_camera":2,"left":2,"l_c":1,"_l/":1,"/l_":1,"_l_":1,"cam":1,"stereo":1,"robot":0.5,"base":0.5,"wheel":-2,"right":-2,"_r_":-2})
	find_possible_tf_frames_for_topic(bag, frames_dict, frames_roots, assignments, "camera_right", "camera_right_tf",
                                          wanted_world_frames = ["world","odom"], wanted_child_frames = ["rgb","right_camera","right","r_c","_r/","/r_","_r_","cam","stereo"], 
	                                  unwanted_child_frames = ["robot","base","wheel","finger","depth","_d_","left","_l_","/l_","_l/"],
	                                  frames_costs = {"rgb":1,"right_camera":2,"right":2,"r_c":1,"_r/":1,"/r_":1,"_r_":1,"cam":1,"stereo":1,"robot":0.5,"base":0.5,"wheel":-2,"left":-2,"_l_":-2})
	find_possible_tf_frames_for_topic(bag, frames_dict, frames_roots, assignments, "camera_depth", "camera_depth_tf",
                                          wanted_world_frames = ["world","odom"], wanted_child_frames = ["depth","_d_","_d/","/d_"], 
	                                  unwanted_child_frames = ["robot","base"],
	                                  frames_costs = {"depth":2,"_d_":2,"world":1, "odom":0.5, "cam":2, "stereo":1, "robot":0.5, "base":0.5})
	return assignments

def create_file(bag_file_path):
	bag=rosbag.Bag(bag_file_path)
	topics = extract_topics(bag)
	assignments = match_topic_types(bag)
	assignments = match_tf_types(bag, assignments)
	return json.dumps(assignments, separators=(',', ':'))

if __name__ == '__main__':
	# usage:
	# ./bag_info.py <path_to_bag> <name_for_json_file>=SCREEN(by default)
	if len(sys.argv) != 2 and len(sys.argv) != 3:
		print("usage:\n./bag_info.py <path_to_bag> <path_for_json_file>=SCREEN(by default)")
	path_to_bag = sys.argv[1]
	if len(sys.argv) == 3:
		file = open(sys.argv[2],'w')
		file.write(create_file(path_to_bag))
	else:
		print(create_file(path_to_bag))

	

'''
#bag=rosbag.Bag("/home/user/data/2011-01-25-06-29-26.bag")
#bag=rosbag.Bag("/home/user/data/2011-01-27-07-49-54.bag")
#bag=rosbag.Bag("/home/user/data/2011-04-11-07-34-27.bag")
bag=rosbag.Bag("/home/user/data/rgbd_dataset_freiburg2_pioneer_360.bag")
topics = extract_topics(bag)
assignments = match_topic_types(topics.items())
print(assignments)
#################################### print topics #############################################           
tab = texttable.Texttable()                                                                   #
tab.header(["topic name","msgs type","msgs count","connections","frequency"])                 #
for topic, info in topics.items():                                                            #
	tab.add_row((topic,info.msg_type,info.message_count,info.connections,info.frequency)) #
print(tab.draw())                                                                             #
###############################################################################################
frames_dict,frames_roots = tree_frames(bag)
######## print tf frames #############
print_tree(frames_dict,frames_roots) #
######################################
laser_frames = extract_parrent_and_child_frames(frames_dict,frames_roots,["world","odom"],["laser","robot","base"])
camera_frames = extract_parrent_and_child_frames(frames_dict,frames_roots,["world","odom"],["cam","stereo","robot","base"])
laser_costs = {"world":1, "odom":1, "laser":1, "robot":0.5, "base":0.5}
camera_costs = {"world":1, "odom":0.5, "cam":2, "stereo":1, "robot":0.5, "base":0.5}
print("laser frames:")
#laser_parents, laser_children = range_by_cost(laser_frames, laser_costs)
#assignments["laser_world_tf_frame"] = laser_parents
#assignments["laser_base_tf_frame"] = laser_children
#print(laser_parents, laser_children)
assignments["laser_tf"] = range_by_cost(laser_frames, laser_costs)
 
print("camera frames:")
#camera_parents, camera_children = range_by_cost(camera_frames, camera_costs)
#assignments["camera_world_tf_frame"] = camera_parents
#assignments["camera_base_tf_frame"] = camera_children
#print(camera_parents, camera_children)
assignments["camera_tf"] = range_by_cost(camera_frames, camera_costs)
print("####################total###################")
print(assignments)
with open('file.json', 'w') as f:
	f.write(json.dumps(assignments))'''
