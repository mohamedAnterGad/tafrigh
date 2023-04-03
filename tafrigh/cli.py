import json
import os
import sys
import warnings

from typing import Any, Dict, List

import tqdm
import whisper

from tafrigh.types.transcript_type import TranscriptType

from tafrigh.utils import cli_utils
from tafrigh.utils import transcript_utils
from tafrigh.utils import whisper_utils
from tafrigh.utils import yt_dlp_utils


TRANSCRIPT_WRITE_FUNC = {
    TranscriptType.VTT: transcript_utils.write_vtt,
    TranscriptType.SRT: transcript_utils.write_srt,
}


def main():
    args = cli_utils.parse_args(sys.argv[1:])

    farrigh(
        urls=args.urls,
        model_name_or_ct2_model_path=args.model_name_or_ct2_model_path,
        task=args.task,
        language=args.language,
        beam_size=args.beam_size,
        ct2_compute_type=args.ct2_compute_type,
        min_words_per_segment=args.min_words_per_segment,
        format=args.format,
        output_txt_file=args.output_txt_file,
        save_yt_dlp_responses=args.save_yt_dlp_responses,
        output_dir=args.output_dir,
        verbose=args.verbose,
    )

    
def farrigh_audio(
    audio_files: List[str],
    model_name_or_ct2_model_path: str,
    task: str,
    language: str,
    beam_size: int,
    ct2_compute_type: str,
    min_words_per_segment: int,
    format: TranscriptType,
    output_txt_file: bool,
    save_yt_dlp_responses: bool,
    output_dir: str,
    verbose: bool,
    audio_dir: str,
) -> None:
    prepare_output_dir(output_dir)

    model, language = whisper_utils.load_model(
        model_name_or_ct2_model_path,
        language,
        ct2_compute_type,
    )

#     for url in tqdm.tqdm(urls, desc='URLs'):
#         url_data = process_url(url, save_yt_dlp_responses, output_dir)
    #print("in farrigh audio : " , output_dir)
    for element in tqdm.tqdm(audio_files, desc='audio files'):
        segments = process_file_audio(element, model, task, language, beam_size, audio_dir, verbose)
        segments = compact_segments(segments, min_words_per_segment)
        #print("before sending to write outputs : " , output_dir)
        write_outputs({"id": element}, segments, format, output_txt_file, output_dir)
        #print(type(element))


            
            

def farrigh(
    urls: List[str],
    model_name_or_ct2_model_path: str,
    task: str,
    language: str,
    beam_size: int,
    ct2_compute_type: str,
    min_words_per_segment: int,
    format: TranscriptType,
    output_txt_file: bool,
    save_yt_dlp_responses: bool,
    output_dir: str,
    verbose: bool,
) -> None:
    prepare_output_dir(output_dir)

    model, language = whisper_utils.load_model(
        model_name_or_ct2_model_path,
        language,
        ct2_compute_type,
    )

    for url in tqdm.tqdm(urls, desc='URLs'):
        url_data = process_url(url, save_yt_dlp_responses, output_dir)

        for element in tqdm.tqdm(url_data, desc='URL elements'):
            segments = process_file(element, model, task, language, beam_size, output_dir, verbose)
            segments = compact_segments(segments, min_words_per_segment)
            write_outputs(element, segments, format, output_txt_file, output_dir)
            


def prepare_output_dir(output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)


def process_url(url: str, save_yt_dlp_responses: bool, output_dir: str) -> List[Dict[str, Any]]:
    return_data = None
    url_data = yt_dlp_utils.download_and_get_url_data(url, output_dir)

    if '_type' in url_data and url_data['_type'] == 'playlist':
        for entry in url_data['entries']:
            for requested_download in entry['requested_downloads']:
                del requested_download['__postprocessors']

        return_data = url_data['entries']
    else:
        for requested_download in url_data['requested_downloads']:
            del requested_download['__postprocessors']

        return_data = [url_data]

    if save_yt_dlp_responses:
        with open(os.path.join(output_dir, f"{url_data['id']}.json"), 'w', encoding='utf-8') as fp:
            json.dump(url_data, fp, indent=4, ensure_ascii=False)

    return return_data


def process_file_audio(
    audio_file: str,
    model: whisper.Whisper,
    task: str,
    language: str,
    beam_size: int,
    output_dir: str,
    verbose: bool,
) -> List[Dict[str, Any]]:
    warnings.filterwarnings('ignore')
    segments = whisper_utils.transcript_audio(
        f"{audio_file}",
        model,
        task,
        language,
        beam_size,
        output_dir,
        verbose,
    )
    warnings.filterwarnings('default')

    return segments


def process_file(
    url_data: Dict[str, Any],
    model: whisper.Whisper,
    task: str,
    language: str,
    beam_size: int,
    output_dir: str,
    verbose: bool,
) -> List[Dict[str, Any]]:
    warnings.filterwarnings('ignore')
    segments = whisper_utils.transcript_audio(
        f"{url_data['id']}.m4a",
        model,
        task,
        language,
        beam_size,
        output_dir,
        verbose,
    )
    warnings.filterwarnings('default')

    return segments


def compact_segments(segments: List[Dict[str, Any]], min_words_per_segment: int) -> List[Dict[str, Any]]:
    if min_words_per_segment == 0:
        return segments

    compacted_segments = list()
    tmp_segment = None

    for segment in segments:
        if tmp_segment:
            tmp_segment['text'] += f" {segment['text'].strip()}"
            tmp_segment['end'] = segment['end']

            if len(tmp_segment['text'].split()) >= min_words_per_segment:
                compacted_segments.append(tmp_segment)
                tmp_segment = None
        elif len(segment['text'].split()) < min_words_per_segment:
            tmp_segment = segment
        elif len(segment['text'].split()) >= min_words_per_segment:
            compacted_segments.append(segment)

    if tmp_segment:
        compacted_segments.append(tmp_segment)

    return compacted_segments


def write_outputs(
    url_data: Dict[str, Any],
    segments: List[Dict[str, Any]],
    format: TranscriptType,
    output_txt_file: bool,
    output_dir: str,
) -> None:
    if format != TranscriptType.NONE:
        with open(os.path.join(output_dir, f"{url_data['id']}.{format}"), 'w', encoding='utf-8') as fp:
            TRANSCRIPT_WRITE_FUNC[format](segments, file=fp)

    if output_txt_file:
        #print("in write outputs : " , output_dir)
        #print("after os.join: " , os.path.join(output_dir , f"{url_data['id']}.txt") )
        with open(os.path.join(output_dir , f"{url_data['id']}.txt"), 'w', encoding='utf-8') as fp:
            fp.write('\n'.join(list(map(lambda segment: segment['text'].strip(), segments))))
            fp.write('\n')
        


if __name__ == '__main__':
    main()
