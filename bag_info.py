#! /usr/bin/python3

import rosbag
from  anytree import Node, RenderTree
import texttable

bag=rosbag.Bag("/home/user/data/2011-01-25-06-29-26.bag")
topics = bag.get_type_and_topic_info().topics
tab = texttable.Texttable()
tab.header(["topic name","msgs type","msgs count","connections","frequency"])
for topic, info in topics.items():
	tab.add_row((topic,info.msg_type,info.message_count,info.connections,info.frequency))
print(tab.draw())

first_message = True
begin_time = 0
frames_list = {}
for topic, msg, t in bag.read_messages(topics=["/tf"]):
	if first_message == True:
		begin_time = t.secs
		first_message = False
	if abs(t.secs - begin_time) > 5:
		break
	for transform in msg.transforms:
		if transform.header.frame_id not in frames_list:
			frames_list[transform.header.frame_id] = Node(transform.header.frame_id)
			head = frames_list[transform.header.frame_id]
		if transform.child_frame_id not in frames_list:
			frames_list[transform.child_frame_id] = Node(transform.child_frame_id,
			                                             parent=frames_list[transform.header.frame_id])
		else:
			frames_list[transform.child_frame_id].parent=frames_list[transform.header.frame_id]

for pre, fill, node in RenderTree(head.root):
	print("%s%s" % (pre,node.name))
