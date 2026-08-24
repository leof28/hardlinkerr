import pytest
from bridge import _sonarr_folder_name

@pytest.mark.parametrize("raw_path, expected", [
    ("/data/media/tv/My Show", "My Show"),
    ("C:\\data\\media\\tv\\My Show", "My Show"),
    ("/data/media/tv/My Show/", "My Show"),
    ("C:\\data\\media\\tv\\My Show\\", "My Show"), # C:\data\media\tv\My Show\ -> C:/data/media/tv/My Show/ -> rstrip -> C:/data/media/tv/My Show -> My Show
    ("", ""),
    ("just_folder_name", "just_folder_name"),
    ("just_folder_name/", "just_folder_name"),
    ("just_folder_name\\", "just_folder_name") # just_folder_name\ -> just_folder_name/ -> rstrip -> just_folder_name
])
def test_sonarr_folder_name_valid_paths(raw_path, expected):
    assert _sonarr_folder_name(raw_path) == expected

def test_sonarr_folder_name_none_input():
    with pytest.raises(AttributeError):
        _sonarr_folder_name(None)
