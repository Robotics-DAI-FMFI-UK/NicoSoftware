#!/usr/bin/env python


import logging
import sys
import time
from os.path import abspath, dirname

import cv2
import numpy
import tensorflow as tf
from nicomotion import Motion
from nicovision.VideoDevice import VideoDevice

from _nicoemotionrecognition_internal import (GUIController,
                                              imageProcessingUtil,
                                              modelDictionary, modelLoader)


class EmotionRecognition:
    def __init__(self, device='', robot=None, face=None, faceDetectionDelta=10,
                 voiceEnabled=False, german=False):
        """
        Initialises the EmotionRecognition

        :param device: Target video capture unit
        :type device: str
        :param faceDetectionDelta: Number of frames until face detection is
                                   refreshed
        :type faceDetectionDelta: int
        """
        self._logger = logging.getLogger(__name__)
        self._finalImageSize = (
            1024, 768)  # Size of the final image generated by the demo
        # Initial position for adding the categorical graph in the final image
        self._categoricalInitialPosition = 260
        # Input size for both models: categorical and dimensional
        self._faceSize = (64, 64)
        self._deviceName = device
        self._device = None
        self._categoricalRecognition = None
        self._dimensionalRecognition = None
        self._running = False
        self._facialExpression = face
        self._robot = robot
        self._voiceEnabled = voiceEnabled
        self._german = german

        self._modelCategorical = modelLoader.modelLoader(
            modelDictionary.CategoricaModel)
        self._modelDimensional = modelLoader.modelLoader(
            modelDictionary.DimensionalModel)
        self._graph = tf.get_default_graph()

        self._faceDetectionDelta = faceDetectionDelta
        self._imageProcessing = imageProcessingUtil.imageProcessingUtil(
            faceDetectionDelta)

        self._GUIController = GUIController.GUIController()

        self._not_found_counter = 0
        self._same_emotion_counter = 0

        self.last_exp = ""

    def start(self, showGUI=True, faceTracking=False, mirrorEmotion=False):
        """
        Starts the emotion recognition

        :param showGUI: Whether or not the GUI should be displayed
        :type showGUI: bool
        :param mirrorEmotion: Whether or not the robot should mirror the
                              detected emotion
        :type mirrorEmotion: bool
        """
        if self._running:
            self._logger.warning(
                'Trying to start emotion recognition while already running')
            return
        self._mirrorEmotion = mirrorEmotion
        self._faceTracking = faceTracking
        self._trackingCounter = 0
        self._device = VideoDevice.from_device(self._deviceName)
        self._device.add_callback(self._callback)
        self._device.open()
        self._showGUI = showGUI
        self._running = True

    def stop(self):
        """
        Stops the emotion recognition
        """
        if not self._running:
            self._logger.warning(
                "Trying to stop emotion recognition while it's not running")
            return
        self._device.close()
        self._device = None
        self._categoricalRecognition = None
        self._dimensionalRecognition = None
        cv2.destroyAllWindows()
        self._running = False

    def getDimensionalData(self):
        """
        Returns the dimensional data of the currently detected face (or None
        if there is none)

        :return: Arousal and Valence score (or None if no face detected)
        :rtype: dict
        """
        if not self._running:
            self._logger.warning(
                'Dimensional data requested while emotion recognition not ' +
                'running')
            return None
        if self._dimensionalRecognition is None:
            self._logger.info(
                "No face detected - Dimensional data will be 'None'")
            return None
        return dict(zip(self._modelDimensional.modelDictionary.classsesOrder,
                        map(lambda x: float(float(x[0][0]) * 100),
                            self._dimensionalRecognition)))

    def getCategoricalData(self):
        """
        Returns the categorical data of the currently detected face (or None if
        there is none)

        :return: Neutral, Happiness, Surprise, Sadness, Anger, Disgust, Fear
                 and Contempt percentages (or None if no face detected)
        :rtype: dict
        """
        if not self._running:
            self._logger.warning(
                'Categorical data requested while emotion recognition not ' +
                'running')
            return None
        if self._dimensionalRecognition is None:
            self._logger.info(
                "No face detected - Categorical data will be 'None'")
            return None
        return dict(zip(self._modelCategorical.modelDictionary.classsesOrder,
                        self._categoricalRecognition[0]))

    def getHighestMatchingEmotion(self):
        """
        Returns the name of the highest matching emotion for the currently
        detected face (or None if there is none)

        :return: Neutral, Happiness, Surprise, Sadness, Anger, Disgust, Fear or
                 Contempt (or None if no face detected)
        :rtype: String
        """
        # if self._categoricalRecognition is not None:
        #    max_index = numpy.argmax(self._categoricalRecognition[0])
        #    max_classname = \
        #    self._modelCategorical.modelDictionary.classsesOrder[max_index]
        #    return self._modelCategorical.modelDictionary.classsesOrder[
        #           numpy.argmax(self._categoricalRecognition[0])].lower()
        # return None

        if self._categoricalRecognition is not None:

            if self._categoricalRecognition[0][6] > 15:
                return "fear"
            elif self._categoricalRecognition[0][4] > 20:
                return "anger"
            elif self._categoricalRecognition[0][3] > 15:
                return "sadness"
            elif self._categoricalRecognition[0][3] > 20:
                return "happiness"
            else:
                max_index = numpy.argmax(self._categoricalRecognition[0])
                max_classname = \
                    self._modelCategorical.modelDictionary.classsesOrder[
                        max_index]
            return self._modelCategorical.modelDictionary.classsesOrder[
                numpy.argmax(self._categoricalRecognition[0])].lower()
        return None

    def _callback(self, rval, frame):
        def say(sen):
            import os.path
            import subprocess
            fname = "./wav_cache/" + sen + ".mp3"
            from gtts import gTTS

            # if True:
            try:

                if not (os.path.isfile(fname)):
                    import urllib2
                    urllib2.urlopen('http://216.58.192.142', timeout=1)
                    if self._german:
                        tts = gTTS(text=sen, lang='de', slow=False)
                    else:
                        tts = gTTS(text=sen, lang='en-au', slow=False)

                    # tts.save("/tmp/say.mp3")
                    tts.save(fname)
                comm = ["mpg123", fname]
                subprocess.check_call(comm)
            # else:
            except:
                # Fallback offline tts engine
                import pyttsx3
                engine = pyttsx3.init()
                engine.say(sen)
                engine.runAndWait()

        if frame is not None:
            facePoints, face = self._imageProcessing.detectFace(frame)

            if self._showGUI:
                image = numpy.zeros(
                    (self._finalImageSize[1], self._finalImageSize[0], 3),
                    numpy.uint8)
                image[0:480, 0:640] = frame
                frame = image

            if not len(face) == 0:
                self._not_found_counter = 0
                if self._faceTracking and self._trackingCounter == 0:
                    if self._robot is not None:
                        # (width - center_x)/width * FOV - FOV/2
                        # horizontal
                        angle_z = ((640 - facePoints[0].center().x)
                                   / 640.0 * 60 - 60 / 2.0)
                        # vertikal
                        angle_y = ((480 - facePoints[0].center().y)
                                   / 480.0 * 50 - 50 / 2.0)
                        self._robot.changeAngle("head_z", angle_z, 0.03)
                        self._robot.changeAngle("head_y", -angle_y, 0.03)
                        time.sleep(0.8)
                    else:
                        self._logger.warning(
                            "No robot given on initialisation - skipping " +
                            "face tracking")
                if self._trackingCounter == self._faceDetectionDelta:
                    self._trackingCounter = 0
                else:
                    self._trackingCounter += 1
                face = self._imageProcessing.preProcess(face, self._faceSize)
                with self._graph.as_default():
                    self._categoricalRecognition = \
                        self._modelCategorical.classify(face)
                    self._dimensionalRecognition = \
                        self._modelDimensional.classify(face)

                if self._mirrorEmotion and self._facialExpression is not None:
                    if self.last_exp != self.getHighestMatchingEmotion():
                        self._same_emotion_counter = 0
                        self.last_exp = self.getHighestMatchingEmotion()
                        self._facialExpression.sendFaceExpression(
                            self.last_exp)
                    else:
                        self._same_emotion_counter += 1

                        if(self._voiceEnabled
                                and self._same_emotion_counter == 3):
                            if self.last_exp == "happiness":
                                import random
                                if self._german:
                                    sents = [
                                        ("Ich bin froehlich, " +
                                         "wenn Du es auch bist!"),
                                        ("Was fuer ein schoener Tag heute " +
                                         "ist, nicht wahr?"),
                                        "Du bist gerade gluecklich, stimmts?"
                                    ]
                                else:
                                    sents = [
                                        "I am happy, if YOU are happy.",
                                        "What a nice day, right?",
                                        "You are happy right now, are you?"
                                    ]
                                say(random.choice(sents))
                            if self.last_exp == "surprise":
                                import random
                                if self._german:
                                    sents = [
                                        ("Du siehst ueberrascht aus. " +
                                         "Was ist denn los?"),
                                        ("Bist Du ueberrascht, was fuer ein " +
                                         "smarter Roboter ich bin?"),
                                        ("Das ist eine Ueberraschung, " +
                                         "nicht wahr?")
                                    ]
                                else:
                                    sents = [
                                        ("You look surprised. Is everything" +
                                         " alright?"),
                                        ("Are you surprised, what a smart " +
                                         "robot I am?"),
                                        "This is a surprise, right?"
                                    ]
                                say(random.choice(sents))
                            if self.last_exp == "anger":
                                import random
                                if self._german:
                                    sents = [
                                        ("Du siehst so aergerlich aus, ist " +
                                         "alles in Ordnung?"),
                                        "aeh Digga, ich bin auch sauer!",
                                        ("Was ist Dir denn ueber die Leber " +
                                         "gelaufen?")
                                    ]
                                else:
                                    sents = [
                                        ("You look angry. " +
                                         "Is everything alright?"),
                                        "I am angry as well!",
                                        "What went wrong?"]
                                say(random.choice(sents))
                            if self.last_exp == "fear":
                                import random
                                if self._german:
                                    sents = [
                                        "Hast Du vor etwas Angst? " +
                                        "Was ist denn hier gefaehrlich?",
                                        "Ich bin ganz harmlos! " +
                                        "Du musst keine Angst vor mir haben!",
                                        "Du siehst aus, als haettest Du " +
                                        "einen Geist gesehen! " +
                                        "Da bekomme ich auch Angst"]
                                else:
                                    sents = [
                                        "Do you fear something?. " +
                                        "What is dangerous here?",
                                        "I am harmless! " +
                                        "You do not have to fear me",
                                        "You look like you have seen a " +
                                        "ghost, but that is only me!"]
                                say(random.choice(sents))

                if self._showGUI:
                    frame = self._GUIController.createDetectedFacGUI(
                        frame, facePoints,
                        self._modelCategorical.modelDictionary,
                        self._categoricalRecognition)
                    frame = self._GUIController.createDimensionalEmotionGUI(
                        self._dimensionalRecognition, frame,
                        self._categoricalRecognition,
                        self._modelCategorical.modelDictionary)
                    frame = self._GUIController.createCategoricalEmotionGUI(
                        self._categoricalRecognition, frame,
                        self._modelCategorical.modelDictionary,
                        initialPosition=self._categoricalInitialPosition)
            else:
                self._categoricalRecognition = None
                self._dimensionalRecognition = None
                if self._faceTracking:
                    self._not_found_counter += 1
                    print "Saw nothing: " + str(self._not_found_counter)
                    if self._not_found_counter > 50:

                        # After  frames of not detecting something, return to
                        # mid position
                        self._not_found_counter = 0
                        if self._robot is not None:
                            from random import randint

                            self._robot.setAngle(
                                "head_z", 0 + randint(-15, 15), 0.01)
                            self._robot.setAngle(
                                "head_y", -30 + randint(-10, 10), 0.01)
                        else:
                            self._logger.warning(
                                "No robot given on initialisation - " +
                                "skipping face tracking")

            if self._showGUI:
                # Display the resulting frame
                cv2.imshow('Visual Emotion Recognition', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    # break
                    return