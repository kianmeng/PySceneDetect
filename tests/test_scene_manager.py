# -*- coding: utf-8 -*-
#
#            PySceneDetect: Python-Based Video Scene Detector
#   -------------------------------------------------------------------
#     [  Site:    https://scenedetect.com                           ]
#     [  Docs:    https://scenedetect.com/docs/                     ]
#     [  Github:  https://github.com/Breakthrough/PySceneDetect/    ]
#
# Copyright (C) 2014 Brandon Castellano <http://www.bcastell.com>.
# PySceneDetect is licensed under the BSD 3-Clause License; see the
# included LICENSE file, or visit one of the above pages for details.
#
"""PySceneDetect scenedetect.scene_manager Tests

This file includes unit tests for the scenedetect.scene_manager.SceneManager class,
which applies SceneDetector algorithms on VideoStream backends.
"""

# pylint: disable=invalid-name

import glob
import os
import os.path
from typing import List

from scenedetect._scene_loader import SceneLoader
from scenedetect.backends.opencv import VideoStreamCv2
from scenedetect.detectors import AdaptiveDetector, ContentDetector
from scenedetect.frame_timecode import FrameTimecode
from scenedetect.scene_manager import SceneManager, save_images, write_scene_list

TEST_VIDEO_START_FRAMES_ACTUAL = [150, 180, 394]


def test_scene_list(test_video_file):
    """Test SceneManager get_scene_list method with VideoStreamCv2/ContentDetector."""
    video = VideoStreamCv2(test_video_file)
    sm = SceneManager()
    sm.add_detector(ContentDetector())

    video_fps = video.frame_rate
    start_time = FrameTimecode('00:00:05', video_fps)
    end_time = FrameTimecode('00:00:15', video_fps)

    assert end_time.get_frames() > start_time.get_frames()

    video.seek(start_time)
    sm.auto_downscale = True

    num_frames = sm.detect_scenes(video=video, end_time=end_time)

    assert num_frames == (end_time.get_frames() - start_time.get_frames())

    scene_list = sm.get_scene_list()
    assert scene_list
    # Each scene is in the format (Start Timecode, End Timecode)
    assert len(scene_list[0]) == 2

    for i, _ in enumerate(scene_list):
        assert scene_list[i][0].get_frames() < scene_list[i][1].get_frames()
        if i > 0:
            # Ensure frame list is sorted (i.e. end time frame of
            # one scene is equal to the start time of the next).
            assert scene_list[i - 1][1] == scene_list[i][0]


def test_get_scene_list_start_in_scene(test_video_file):
    """Test SceneManager `get_scene_list()` method with the `start_in_scene` flag."""
    video = VideoStreamCv2(test_video_file)
    sm = SceneManager()
    sm.add_detector(ContentDetector())

    video_fps = video.frame_rate
    # End time must be short enough that we won't detect any scenes.
    end_time = FrameTimecode(25, video_fps)
    sm.auto_downscale = True
    sm.detect_scenes(video=video, end_time=end_time)
    # Should be an empty list.
    assert len(sm.get_scene_list()) == 0
    # Should be a list with a single element spanning the video duration.
    scene_list = sm.get_scene_list(start_in_scene=True)
    assert len(scene_list) == 1
    assert scene_list[0][0] == 0
    assert scene_list[0][1] == end_time


def test_save_images(test_video_file):
    """Test scenedetect.scene_manager.save_images function."""
    video = VideoStreamCv2(test_video_file)
    sm = SceneManager()
    sm.add_detector(ContentDetector())

    image_name_glob = 'scenedetect.tempfile.*.jpg'
    image_name_template = 'scenedetect.tempfile.$SCENE_NUMBER.$IMAGE_NUMBER'

    try:
        video_fps = video.frame_rate
        scene_list = [(FrameTimecode(start, video_fps), FrameTimecode(end, video_fps))
                      for start, end in [(0, 100), (200, 300), (300, 400)]]

        image_filenames = save_images(
            scene_list=scene_list,
            video=video,
            num_images=3,
            image_extension='jpg',
            image_name_template=image_name_template)

        # Ensure images got created, and the proper number got created.
        total_images = 0
        for scene_number in image_filenames:
            for path in image_filenames[scene_number]:
                assert os.path.exists(path)
                total_images += 1

        assert total_images == len(glob.glob(image_name_glob))

    finally:
        for path in glob.glob(image_name_glob):
            os.remove(path)


# TODO: Test other functionality against zero width scenes.
def test_save_images_zero_width_scene(test_video_file):
    """Test scenedetect.scene_manager.save_images guards against zero width scenes."""
    video = VideoStreamCv2(test_video_file)
    image_name_glob = 'scenedetect.tempfile.*.jpg'
    image_name_template = 'scenedetect.tempfile.$SCENE_NUMBER.$IMAGE_NUMBER'
    try:
        video_fps = video.frame_rate
        scene_list = [(FrameTimecode(start, video_fps), FrameTimecode(end, video_fps))
                      for start, end in [(0, 0), (1, 1), (2, 3)]]
        NUM_IMAGES = 10
        image_filenames = save_images(
            scene_list=scene_list,
            video=video,
            num_images=10,
            image_extension='jpg',
            image_name_template=image_name_template)
        assert len(image_filenames) == 3
        assert all(len(image_filenames[scene]) == NUM_IMAGES for scene in image_filenames)
        total_images = 0
        for scene_number in image_filenames:
            for path in image_filenames[scene_number]:
                assert os.path.exists(path)
                total_images += 1
        assert total_images == len(glob.glob(image_name_glob))
    finally:
        for path in glob.glob(image_name_glob):
            os.remove(path)


# TODO: This would be more readable if the callbacks were defined within the test case, e.g.
# split up the callback function and callback lambda test cases.
# pylint: disable=unused-argument, unnecessary-lambda
class FakeCallback(object):
    """Fake callback used for testing. Tracks the frame numbers the callback was invoked with."""

    def __init__(self):
        self.scene_list: List[int] = []

    def get_callback_lambda(self):
        """For testing using a lambda.."""
        return lambda image, frame_num: self._callback(image, frame_num)

    def get_callback_func(self):
        """For testing using a callback function."""

        def callback(image, frame_num):
            nonlocal self
            self._callback(image, frame_num)

        return callback

    def _callback(self, image, frame_num):
        self.scene_list.append(frame_num)


# pylint: enable=unused-argument, unnecessary-lambda


def test_detect_scenes_callback(test_video_file):
    """Test SceneManager detect_scenes method with a callback function.

    Note that the API signature of the callback will undergo breaking changes in v1.0.
    """
    video = VideoStreamCv2(test_video_file)
    sm = SceneManager()
    sm.add_detector(ContentDetector())

    fake_callback = FakeCallback()

    video_fps = video.frame_rate
    start_time = FrameTimecode('00:00:05', video_fps)
    end_time = FrameTimecode('00:00:15', video_fps)
    video.seek(start_time)
    sm.auto_downscale = True

    _ = sm.detect_scenes(
        video=video, end_time=end_time, callback=fake_callback.get_callback_lambda())
    scene_list = sm.get_scene_list()
    assert [start for start, end in scene_list] == TEST_VIDEO_START_FRAMES_ACTUAL
    assert fake_callback.scene_list == TEST_VIDEO_START_FRAMES_ACTUAL[1:]

    # Perform same test using callback function instead of lambda.
    sm.clear()
    sm.add_detector(ContentDetector())
    fake_callback = FakeCallback()
    video.seek(start_time)

    _ = sm.detect_scenes(video=video, end_time=end_time, callback=fake_callback.get_callback_func())
    scene_list = sm.get_scene_list()
    assert [start for start, end in scene_list] == TEST_VIDEO_START_FRAMES_ACTUAL
    assert fake_callback.scene_list == TEST_VIDEO_START_FRAMES_ACTUAL[1:]


def test_detect_scenes_callback_adaptive(test_video_file):
    """Test SceneManager detect_scenes method with a callback function and a detector which
    requires frame buffering.

    Note that the API signature of the callback will undergo breaking changes in v1.0.
    """
    video = VideoStreamCv2(test_video_file)
    sm = SceneManager()
    sm.add_detector(AdaptiveDetector())

    fake_callback = FakeCallback()

    video_fps = video.frame_rate
    start_time = FrameTimecode('00:00:05', video_fps)
    end_time = FrameTimecode('00:00:15', video_fps)
    video.seek(start_time)
    sm.auto_downscale = True

    _ = sm.detect_scenes(
        video=video, end_time=end_time, callback=fake_callback.get_callback_lambda())
    scene_list = sm.get_scene_list()
    assert [start for start, end in scene_list] == TEST_VIDEO_START_FRAMES_ACTUAL
    assert fake_callback.scene_list == TEST_VIDEO_START_FRAMES_ACTUAL[1:]

    # Perform same test using callback function instead of lambda.
    sm.clear()
    sm.add_detector(AdaptiveDetector())
    fake_callback = FakeCallback()
    video.seek(start_time)

    _ = sm.detect_scenes(video=video, end_time=end_time, callback=fake_callback.get_callback_func())
    scene_list = sm.get_scene_list()
    assert [start for start, end in scene_list] == TEST_VIDEO_START_FRAMES_ACTUAL
    assert fake_callback.scene_list == TEST_VIDEO_START_FRAMES_ACTUAL[1:]


def test_scene_loader(tmp_path, test_movie_clip):
    """Test `SceneLoader` loading from CSV written by `write_scene_list`."""

    def _detect(video, detector, start, end):
        """Helper function similar to `scenedetect.detect()` but using an existing VideoStream."""
        scene_manager = SceneManager()
        scene_manager.add_detector(detector)
        scene_manager.auto_downscale = True
        video.seek(start)
        scene_manager.detect_scenes(video=video, end_time=end)
        return scene_manager.get_scene_list()

    # Generate scene list.
    video = VideoStreamCv2(test_movie_clip)
    scene_list = _detect(
        video=video,
        detector=ContentDetector(),
        start=FrameTimecode('00:00:50', video.frame_rate),
        end=FrameTimecode('00:01:19', video.frame_rate))

    # Save and see if we get the same result.
    with open(tmp_path / "scenes.csv", "w") as csv_file:
        write_scene_list(csv_file, scene_list, include_cut_list=True)
    from_csv = _detect(
        video=VideoStreamCv2(test_movie_clip),
        detector=SceneLoader(tmp_path / "scenes.csv"),
        start=FrameTimecode('00:00:50', video.frame_rate),
        end=FrameTimecode('00:01:19', video.frame_rate))
    assert from_csv == scene_list

    # Test without the cut list as a header as well.
    with open(tmp_path / "scenes-nocuts.csv", "w") as csv_file:
        write_scene_list(csv_file, scene_list, include_cut_list=False)
    from_csv = _detect(
        video=VideoStreamCv2(test_movie_clip),
        detector=SceneLoader(tmp_path / "scenes-nocuts.csv"),
        start=FrameTimecode('00:00:50', video.frame_rate),
        end=FrameTimecode('00:01:19', video.frame_rate))
    assert from_csv == scene_list
