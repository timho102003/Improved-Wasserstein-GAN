import scipy.misc as misc
import time
import tensorflow as tf
from architecture import netD, netG
import numpy as np
import random
import ntpath
import sys
import cv2
import os
from skimage import color
import argparse
import data_ops

if __name__ == '__main__':

   parser = argparse.ArgumentParser()
   parser.add_argument('--DATASET',    required=False,type=str,help='The DATASET to use',default='celeba')
   parser.add_argument('--DATA_DIR',   required=True,type=str,help='Directory where data is')
   parser.add_argument('--BATCH_SIZE', required=False,type=int,help='Batch size',default=64)
   parser.add_argument('--LAMBDA',     required=False,type=float,help='Lambda value',default=10.0)
   parser.add_argument('--NUM_D',      required=False,type=int,help='Critic number',default=5)
   a = parser.parse_args()

   DATASET        = a.DATASET
   DATA_DIR       = a.DATA_DIR
   BATCH_SIZE     = a.BATCH_SIZE
   LAMBDA         = a.LAMBDA
   NUM_D          = a.NUM_D
   CHECKPOINT_DIR = 'checkpoints/'+DATASET+'/'
   IMAGES_DIR     = CHECKPOINT_DIR+'images/'

   try: os.makedirs(IMAGES_DIR)
   except: pass
   
   # placeholders for data going into the network
   global_step = tf.Variable(0, name='global_step', trainable=False)
   z           = tf.placeholder(tf.float32, shape=(BATCH_SIZE, 100), name='z')

   train_images_list = data_ops.loadData(DATA_DIR, DATASET)
   filename_queue    = tf.train.string_input_producer(train_images_list)
   real_images       = data_ops.read_input_queue(filename_queue, BATCH_SIZE)

   # generated images
   gen_images = netG(z, BATCH_SIZE)

   # get the output from D on the real and fake data
   errD_real = netD(real_images, BATCH_SIZE)
   errD_fake = netD(gen_images, BATCH_SIZE, reuse=True)

   # cost functions
   #errD = tf.reduce_mean(errD_real - errD_fake)
   errD = tf.reduce_mean(errD_real) - tf.reduce_mean(errD_fake)
   errG = -tf.reduce_mean(errD_fake)

   '''
   epsilon = tf.random_uniform([], 0.0, 1.0)
   x_hat   = epsilon * real_images + (1 - epsilon) * gen_images
   d_hat   = netD(x_hat, BATCH_SIZE, reuse=True)

   ddx = tf.gradients(d_hat, x_hat)[0]
   ddx = tf.sqrt(tf.reduce_sum(tf.square(ddx), axis=1))
   ddx = tf.reduce_mean(tf.square(ddx - 1.0))

   errD = errD + LAMBDA*ddx
   '''
   epsilon = tf.random_uniform([BATCH_SIZE,1], 0.0, 1.0)
   differences  = gen_images - real_images
   interpolates = real_images + (epsilon*differences)
   gradients = tf.gradients(netD(interpolates, BATCH_SIZE, reuse=True), [interpolates])[0]
   slopes = tf.sqrt(tf.reduce_sum(tf.square(gradients), reduction_indices=[1]))
   gradient_penalty = tf.reduce_mean((slopes-1.)**2)
   errD += LAMBDA*gradient_penalty

   # tensorboard summaries
   tf.summary.scalar('d_loss', errD)
   tf.summary.scalar('g_loss', errG)
   merged_summary_op = tf.summary.merge_all()

   # get all trainable variables, and split by network G and network D
   t_vars = tf.trainable_variables()
   d_vars = [var for var in t_vars if 'd_' in var.name]
   g_vars = [var for var in t_vars if 'g_' in var.name]

   # optimize G
   G_train_op = tf.train.AdamOptimizer(learning_rate=1e-4,beta1=0.,beta2=0.9).minimize(errG, var_list=g_vars, global_step=global_step)

   # optimize D
   D_train_op = tf.train.AdamOptimizer(learning_rate=1e-4,beta1=0.,beta2=0.9).minimize(errD, var_list=d_vars)

   gpu_options = tf.GPUOptions(allow_growth=True)

   saver = tf.train.Saver(max_to_keep=1)
   init = tf.group(tf.global_variables_initializer(), tf.local_variables_initializer())
   sess  = tf.Session(config=tf.ConfigProto(gpu_options=gpu_options))
   sess.run(init)

   summary_writer = tf.summary.FileWriter(CHECKPOINT_DIR+'/'+'logs/', graph=tf.get_default_graph())

   tf.add_to_collection('G_train_op', G_train_op)
   tf.add_to_collection('D_train_op', D_train_op)
   
   # restore previous model if there is one
   ckpt = tf.train.get_checkpoint_state(CHECKPOINT_DIR)
   if ckpt and ckpt.model_checkpoint_path:
      print "Restoring previous model..."
      try:
         saver.restore(sess, ckpt.model_checkpoint_path)
         print "Model restored"
      except:
         print "Could not restore model"
         pass
   
   ########################################### training portion

   step = sess.run(global_step)
   
   coord = tf.train.Coordinator()
   threads = tf.train.start_queue_runners(sess, coord=coord)

   while True:
      
      start = time.time()
      
      # now train the generator once! use normal distribution, not uniform!!
      batch_z = np.random.normal(-1.0, 1.0, size=[BATCH_SIZE, 100]).astype(np.float32)
      sess.run(G_train_op, feed_dict={z:batch_z})

      for critic_itr in range(NUM_D):
         batch_z = np.random.normal(-1.0, 1.0, size=[BATCH_SIZE, 100]).astype(np.float32)
         sess.run(D_train_op, feed_dict={z:batch_z})


      # now get all losses and summary *without* performing a training step - for tensorboard
      D_loss, G_loss, summary = sess.run([errD, errG, merged_summary_op], feed_dict={z:batch_z})
      summary_writer.add_summary(summary, step)

      print 'step:',step,'D loss:',D_loss,'G_loss:',G_loss#,'time:',time.time()-start
      step += 1
    
      if step%100 == 0:
         print 'Saving model...'
         saver.save(sess, CHECKPOINT_DIR+'checkpoint-'+str(step))
         saver.export_meta_graph(CHECKPOINT_DIR+'checkpoint-'+str(step)+'.meta')
         batch_z  = np.random.normal(-1.0, 1.0, size=[BATCH_SIZE, 100]).astype(np.float32)
         gen_imgs = sess.run([gen_images], feed_dict={z:batch_z})

         data_ops.saveImage(gen_imgs[0], step, IMAGES_DIR)
         print 'Done saving'



