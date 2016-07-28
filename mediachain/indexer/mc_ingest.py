#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Functions for ingestion of media files into Indexer.

Potential sources include:
- Mediachain blockchain.
- Getty dumps.
- Other media sources.

Scraping / downloading functions also contained here.

Later may be extended to insert media that comes from off-chain into the chain.
"""

from mc_generic import setup_main, group, raw_input_enter, pretty_print, intget, print_config, sleep_loud

import mc_config
import mc_datasets
import mc_neighbors

from time import sleep,time
import json
import os
from os.path import exists, join
from os import mkdir, listdir, makedirs, walk, rename, unlink

from Queue import Queue
from threading import current_thread,Thread

import requests
from random import shuffle
from shutil import copyfile
import sys
from sys import exit

from datetime import datetime
from dateutil import parser as date_parser
from hashlib import md5

from PIL import Image
from cStringIO import StringIO

import binascii
import base64
import base58

import numpy as np

import imagehash
import itertools

import hashlib

from elasticsearch import Elasticsearch
from elasticsearch.helpers import parallel_bulk, scan

data_pat = 'data:image/jpeg;base64,'
data_pat_2 = 'data:image/png;base64,'


def shrink_and_encode_image(s, size = (1024, 1024), to_base64 = True):
    """
    Resize image to small size & base64 encode it.
    """
    
    img = Image.open(StringIO(s))
    
    if (img.size[0] > size[0]) or (img.size[1] > size[1]):
        f2 = StringIO()
        img.thumbnail(size, Image.ANTIALIAS)
        img.convert('RGB').save(f2, "JPEG")
        f2.seek(0)
        s = f2.read()

    if to_base64:        
        return data_pat + base64.b64encode(s)
    
    else:
        return s


def decode_image(s):

    if s.startswith(data_pat):
        ss = s[len(data_pat):]
        
    elif s.startswith(data_pat_2):
        ss = s[len(data_pat_2):]
        
    else:
        assert False,('BAD_DATA_URL',s[:15])

    try:
        rr = base64.b64decode(ss)
    except:
        ## Temporary workaround for broken encoder:
        rr = base64.urlsafe_b64decode(ss)

    return rr


def lookup_cached_image(_id,
                        do_sizes = ['1024x1024','256x256'], #'original', 
                        return_as_urls = True,
                        image_cache_dir = mc_config.MC_IMAGE_CACHE_DIR,
                        image_cache_host = mc_config.MC_IMAGE_CACHE_HOST,
                        ):
    """
    See also: `cache_image()`
    """
    
    if '_' in _id:
        ## TODO: either md5 of native_id or not:
        _id = hashlib.md5(_id).hexdigest()
    
    if not image_cache_dir.endswith('/'):
        image_cache_dir = image_cache_dir + '/'
    
    if not image_cache_host.endswith('/'):
        image_cache_host = image_cache_host + '/'
        
    rh = {}
    
    for size in do_sizes:
        
        dr1 = image_cache_dir + 'hh_' + size + '/'
        
        dr2 = dr1 + _id[:3] + '/'
        
        fn_cache = dr2 + _id + '.jpg'
        
        ## TODO: handle cache misses here?
        
        if return_as_urls:
            rh[size] = image_cache_host + 'hh_' + size + '/' + _id[:3] + '/' + _id + '.jpg'
        
        else:
            
            rh[size] = fn_cache

    print ('lookup_cached_image',rh)
    
    return rh


def cache_image(_id,
                image_base64 = False,
                image_bytes = False,
                do_sizes = ['1024x1024','256x256'], #'original', 
                return_as_urls = True,
                image_cache_dir = mc_config.MC_IMAGE_CACHE_DIR,
                image_cache_host = mc_config.MC_IMAGE_CACHE_HOST,
                ):
    """
    Cache an image for later use by other stages of the pipeline.
    
    Uses plain files for now, because that's what works the best for HTTP serving of image files to the Frontend.
    
    Args:
       _id:            Note - Assumed to be already cryptographically hashed, for even distribution.
       image_base64:   Base64 encoded image content.
       image_bytes:    Image content bytes.
       do_sizes:       Output resized versions with these sizes.
       return_as_urls: Return as URLs, otherwise return filenames.
    
    Process:
       1) Check if hash of image file for this `_id` has changed.
       2) Store (_id -> content_hash) and (_id -> image_content)
    
    Components using this cache:
       - Ingestion via Indexer.
       - Content-based vector calculation.
       - HTTP server for cached images for Frontend.
    
    Open questions:
       - Expiration? Intentionally delaying a decision on this for now.

    See also: `lookup_cached_image()`
    """

    if '_' in _id:
        ## TODO: either md5 of native_id or not:
        _id = hashlib.md5(_id).hexdigest()
    
    assert (image_base64 is not False) or (image_bytes is not False)
    assert not ((image_base64 is not False) and (image_bytes is not False))
    
    if not image_cache_dir.endswith('/'):
        image_cache_dir = image_cache_dir + '/'
    
    if not image_cache_host.endswith('/'):
        image_cache_host = image_cache_host + '/'
    
    rh = {}
    
    for size in do_sizes:
        
        ## Check if file is cached, and has not changed for this ID:
        
        dr1 = image_cache_dir + 'hh_' + size + '/'
        
        dr1_b = image_cache_dir + 'hh_hash/'
        
        dr2 = dr1 + _id[:3] + '/'
                
        fn_h = dr1_b + _id + '.hash'
        
        fn_cache = dr2 + _id + '.jpg'
        
        url = image_cache_host + 'hh_' + size + '/' + _id[:3] + '/' + _id + '.jpg'
        
        hsh = hashlib.md5(image_base64).hexdigest()

        current_cached = False
        if exists(fn_h):
            with open(fn_h) as f:
                r_hsh = f.read()
            if r_hsh == hsh:
                current_cached = True
        
        ## Store image content, return URLs or file paths:
        
        if not current_cached:
            
            if not exists(dr1):
                mkdir(dr1)

            if not exists(dr1_b):
                mkdir(dr1_b)
            
            if not exists(dr2):
                mkdir(dr2)
            
            if image_base64 is not False:
                if image_bytes is False:
                    #image_base64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg=="
                    image_bytes = decode_image(image_base64)
            else:
                assert image_bytes is not False
            
            if size != 'original':
                iw, ih = size.split('x')
                iw, ih = int(iw), int(ih)
            
            try:
                bytes_out = shrink_and_encode_image(image_bytes,
                                                    size = (iw, ih),
                                                    to_base64 = False,
                                                    )
            except:
                print ('BAD_IMAGE_FILE',len(image_bytes),image_bytes[:100])
                continue
                        
            with open(fn_cache, 'w') as f:
                f.write(bytes_out)
            
            with open(fn_h + '.temp', 'w') as f:
                f.write(hsh)

            rename(fn_h + '.temp',
                   fn_h,
                   )
        
        if return_as_urls:
            rh[size] = url

        else:
            rh[size] = fn_cache

    print ('cache_image',rh)
    
    return rh


def ingest_bulk(iter_json = False,
                thread_count = 1,
                index_name = mc_config.MC_INDEX_NAME,
                doc_type = mc_config.MC_DOC_TYPE,
                search_after = False,
                redo_thumbs = True,
                ignore_thumbs = False,
                use_aggressive = True,
                refresh_after = True,
                thumbs_elsewhere = True,
                ):
    """
    Ingest Getty dumps from JSON files.
    
    Currently does not attempt to import media to the Mediachain chain.
    
    Args:
        iter_json:      Iterable of media objects, with `img_data` containing the raw-bytes image data.
        thread_count:   Number of parallel threads to use for ES insertion.
        index_name:     ES index name to use.
        doc_type:       ES document type to use.
        search_after:   Manually inspect ingested records after. Probably not needed anymore.
        redo_thumbs:    Whether to recalcuate 'image_thumb' from 'img_data'.
        ignore_thumbs:  Whether to ignore thumbnail generation entirely.
        use_aggressive: Use slow inserter that immediately indexes & refreshes after each item.
        
        auto_reindex_inactive:   Auto-reindex after `auto_reindex_inactive` seconds of inactivity.
        auto_reindex_max:        Auto-reindex at least every `auto_reindex_max` seconds, regardless of ingestion activity.

        thumbs_elsewhere: Don't store thumbs in ES database. TODO: store thumbs via new shared disk cache system.
    
    Returns:
        Number of inserted records.
    
    Examples:
        See `mc_test.py`
    """
    
    index_settings = {'settings': {'number_of_shards': mc_config.MC_NUMBER_OF_SHARDS_INT,
                                   'number_of_replicas': mc_config.MC_NUMBER_OF_REPLICAS_INT,                             
                                   },
                      'mappings': {doc_type: {'properties': {'title':{'type':'string'},
                                                             'artist':{'type':'string'},
                                                             'collection_name':{'type':'string'},
                                                             'caption':{'type':'string'},
                                                             'editorial_source':{'type':'string'},
                                                             'keywords':{'type':'string', 'index':'not_analyzed'},
                                                             'created_date':{'type':'date'},
                                                             'image_thumb':{'type':'string', 'index':'no'},
                                                             'dedupe_hsh':{'type':'string', 'index':'not_analyzed'},
                                                             },
                                              },
                                   },
                      }
    
    if not iter_json:
        iter_json = mc_datasets.iter_json_getty()
    
    if mc_config.LOW_LEVEL:
        es = mc_neighbors.low_level_es_connect()
        
        if not es.indices.exists(index_name):
            print ('CREATE_INDEX...',index_name)
            es.indices.create(index = index_name,
                              body = index_settings,
                              #ignore = 400, # ignore already existing index
                              )
            
            print('CREATED',index_name)
    else:
        #NOT LOW_LEVEL:
        nes = mc_neighbors.high_level_connect(index_name = index_name,
                                              doc_type = doc_type,
                                              index_settings = index_settings,
                                              use_custom_parallel_bulk = use_aggressive,
                                              )
                
        nes.create_index()
            
    print('INSERTING...')

    def iter_wrap():
        # Put in parallel_bulk() format:

        nnn = 0 

        t0 = time()
        
        for hh in iter_json:
            
            xdoc = {'_op_type': 'index',
                    '_index': index_name,
                    '_type': doc_type,
                    }
            
            hh.update(xdoc)
            
            assert '_id' in hh,hh.keys()

            ## Cache multiple sizes of image, requires `_id` field:

            if ('thumbnail_base64' in hh):

                fns = cache_image(_id = hh['_id'],
                                  image_base64 = hh['thumbnail_base64'],
                                  do_sizes = ['1024x1024','256x256'],
                                  return_as_urls = False,
                                  )

                print ('CACHED_IMAGE',fns)
            else:
                assert False

            
            ## -- START TEMPORARY FOR DEMO:
            ignore_thumbs_elsewhere = False
            if hh.get('source_dataset') == 'getty':
                ignore_thumbs_elsewhere = True
            else:
                print '???',repr(hh.get('source_dataset'))
            ## -- END TEMPORARY FOR DEMO
            
                
            if thumbs_elsewhere and not ignore_thumbs_elsewhere:

                ## Temporarily ignoring image thumbnails. Will switch from storing these in ES, to using the
                ## shared file-based image cache.
                
                if 'img_data' in hh:
                    del hh['img_data']
                
                if 'image_thumb' in hh:
                    del hh['image_thumb']
                
                print 'THUMBS_ELSEWHERE'
            
            elif (hh.get('img_data') == 'NO_IMAGE') or (hh.get('image_thumb') == 'NO_IMAGE'):
                ## One-off ignoring of thumbnail generation via `NO_IMAGE`.
                                
                if 'img_data' in hh:
                    del hh['img_data']
                
                if 'image_thumb' in hh:
                    del hh['image_thumb']
            
            elif not ignore_thumbs:
                if redo_thumbs:
                    # Check existing thumbs meet size & format requirements:

                    if 'img_data' in hh:
                        hh['image_thumb'] = shrink_and_encode_image(decode_image(hh['img_data']))

                    elif 'image_thumb' in hh:
                        hh['image_thumb'] = shrink_and_encode_image(decode_image(hh['image_thumb']))

                    else:
                        print 'CANT_GENERATE_THUMBNAIL'
                        #assert False,'CANT_GENERATE_THUMBNAIL'

                elif 'image_thumb' not in hh:
                    # Generate thumbs from raw data:

                    if 'img_data' in hh:
                        hh['image_thumb'] = shrink_and_encode_image(decode_image(hh['img_data']))

                    else:
                        print 'CANT_GENERATE_THUMBNAIL'
                        #assert False,'CANT_GENERATE_THUMBNAIL'

                if 'img_data' in hh:
                    del hh['img_data']
            
            chh = hh.copy()
            if 'image_thumb' in chh:
                del chh['image_thumb']
            
            if nnn % 100 == 0:
                print 'YIELDING_FOR_INSERT','num:',nnn, 'index_name:',index_name, 'doc_type:',doc_type,'per_second:',nnn / (time() - t0)
            
            nnn += 1
            
            yield hh
    
    gen = iter_wrap()
    
    def non_parallel_bulk(es,
                          the_iter,
                          *args, **kw):
        """
        Aggressive inserter that inserts & refreshes after every item.
        """
        print 'USING: NON_PARALLEL_BULK'
        
        for c,hh in enumerate(the_iter):
            
            #print 'NON_PARALLEL_BULK',repr(hh)[:100],'...'
            
            xaction = hh['_op_type']
            xindex = hh['_index']
            xtype = hh['_type']
            xid = hh['_id']
            
            for k,v in hh.items():
                if k.startswith('_'):
                    del hh[k]
            
            assert xaction == 'index',(xaction,)
            
            #print 'BODY',hh

            ## TODO - re-add batching:
            res = es.index(index = xindex, doc_type = xtype, id = xid, body = hh)
            
            #print 'DONE-NON_PARALLEL_BULK',xaction,xid
            
            yield True,res
            
            if (c > 0) and (c % 1000 == 0):
                t1 = time()
                print ('REFRESH-NON_PARALLEL_BULK',c)
                try:
                    es.indices.refresh(index = xindex)
                except:
                    print 'REFRESH_ERROR'
                print 'REFRESHED',time() - t1
                
                if False:
                    try:
                        import mc_models
                        mc_models.dedupe_reindex_all()
                    except:
                        print '!!! REINDEX_ERROR:'
                        import traceback, sys, os
                        for line in traceback.format_exception(*sys.exc_info()):
                            print line,
                            
        print ('REFRESH-NON_PARALLEL_BULK',c)
        try:
            es.indices.refresh(index = xindex)
        except:
            print 'REFRESH_ERROR'
        print 'REFRESHED'
        
        print 'EXIT-LOOP_NON_PARALLEL_BULK'
        
        
    if use_aggressive:
        use_inserter = non_parallel_bulk
    else:
        use_inserter = parallel_bulk

    is_empty = True
    
    try:
        first = gen.next() ## TODO: parallel_bulk silently eats exceptions. Here's a quick hack to watch for errors.
        is_empty = False
    except StopIteration:
        print '!!!WARN: GOT EMPTY INPUT ITERATOR'

    if not is_empty:
        if mc_config.LOW_LEVEL:
            ii = use_inserter(es,
                              itertools.chain([first], gen),
                              thread_count = thread_count,
                              chunk_size = 1,
                              max_chunk_bytes = 100 * 1024 * 1024, #100MB
                              )
        else:
            ii = nes.parallel_bulk(itertools.chain([first], gen))

        for is_success,res in ii:
            """
            #FORMAT:
            (True,
                {u'index': {u'_id': u'getty_100113781',
                            u'_index': u'getty_test',
                            u'_shards': {u'failed': 0, u'successful': 1, u'total': 1},
                            u'_type': u'image',
                            u'_version': 1,
                            u'status': 201}})
            """
            pass

    rr = False
    
    if refresh_after:
        if mc_config.LOW_LEVEL:
            print ('REFRESHING', index_name)
            es.indices.refresh(index = index_name)
            print ('REFRESHED')
            rr = es.count(index_name)['count']
        else:
            nes.refresh_index()
            rr = nes.count()
        
    return rr


def tail_blockchain(via_cli = False):
    """
    Debugging tool - Watch blocks arrive from blockchain. 
    """
    from mc_simpleclient import SimpleClient

    cur = SimpleClient()
    
    for art in cur.get_artefacts():
        print ('ART:',time(),art)
    

    
def receive_blockchain_into_indexer(last_block_ref = None,
                                    index_name = mc_config.MC_INDEX_NAME,
                                    doc_type = mc_config.MC_DOC_TYPE,
                                    via_cli = False,
                                    ):
    """
    Read media from Mediachain blockchain and write it into Indexer.
    
    Args:
        last_block_ref:  (Optional) Last block ref to start from.
        index_name:      Name of Indexer index to populate.
        doc_type:        Name of Indexer doc type.
    """
    
    from mc_simpleclient import SimpleClient
    
    cur = SimpleClient()
    
    def the_gen():
        ## Convert from blockchain format to Indexer format:
        
        for ref, art in cur.get_artefacts(force_exit = via_cli): ## Force exit after loop is complete, if CLI.
            
            try:
                print 'GOT',art.get('type')
                
                if art['type'] != u'artefact':
                    continue

                meta = art['meta']['data']
                
                rh = {}
                
                ## Copy these keys in from meta. Use tuples to rename keys. Keys can be repeated:

                if False:
                    for kk in [u'caption', u'date_created', u'title', u'artist',
                               u'keywords', u'collection_name', u'editorial_source',
                               '_id',
                               ('_id','getty_id'),
                               ('thumbnail_base64','image_thumb'),
                               ]:

                        if type(kk) == tuple:
                            rh[kk[1]] = meta.get(kk[0], None)
                        elif kk == u'keywords':
                            rh[kk] = ' '.join(meta.get(kk, []))
                        else:
                            rh[kk] = meta.get(kk, None)
                else:
                    ## TODO - Is simply copying everything over, without changes or checks, what we want to do?:
                    
                    rh = meta
                    
                
                #TODO: Phase out `rawRef`:
                if 'raw_ref' in art['meta']:
                    raw_ref = art['meta']['raw_ref']
                elif 'rawRef' in art['meta']:
                    raw_ref = art['meta']['rawRef']
                else:
                    assert False,('RAW_REF',repr(art)[:500])
                
                rh['latest_ref'] = base58.b58encode(raw_ref[u'@link'])
                rh['canonical_ref'] = ref

                ## TODO - use different created date? Phase out `translatedAt`:
                xx = None
                if 'translated_at' in art['meta']:
                    xx = art['meta']['translated_at']
                elif 'translatedAt' in art['meta']:
                    xx = art['meta']['translatedAt']

                if xx is not None:
                    rh['date_created'] = date_parser.parse(xx)

                rhc = rh.copy()
                if 'img_data' in rhc:
                    del rhc['img_data']
                if 'thumbnail_base64' in rhc:
                    del rhc['thumbnail_base64']
                print 'INSERT',rhc
                
                yield rh
            except:
                raise
                print ('!!!ARTEFACT PARSING ERROR:',)
                print repr(art)
                print 'TRACEBACK:'
                import traceback, sys, os
                for line in traceback.format_exception(*sys.exc_info()):
                    print line,
                exit(-1)
                
        print 'END ITER'
    
    ## Do the ingestion:
    
    nn = ingest_bulk(iter_json = the_gen(),
                     #index_name = index_name,
                     #doc_type = doc_type,
                     )
    
    print 'GRPC EXITED SUCCESSFULLY...'

    
    print 'DONE_INGEST',nn


def send_compactsplit_to_blockchain(path_glob = False,
                                    max_num = 5,
                                    normalizer_name = False,
                                    via_cli = False,
                                    ):
    """
    Read in from compactsplit dumps, write to blockchain.
    
    Why this endpoint instead of the `mediachain.client` endpoint? This endpoint allows us to do sophisticated
    dedupe analysis prior to sending media to the blockchain.
    
    Args:
        path_glob:             Directory containing compactsplit files.
        max_num:               End ingestion early after `max_num` records. For testing.
        index_name:            Name of Indexer index to populate.
        doc_type:              Name of Indexer doc type.
        normalizer_name:       Name or function for applying normalization / translation to records.
    """
    
    import sys
    
    from mc_datasets import iter_compactsplit
    from mc_generic import set_console_title
    from mc_normalize import apply_normalizer, normalizer_names
    
    from mc_simpleclient import SimpleClient
    
    if via_cli: 
        if (len(sys.argv) < 4):
            print ('Usage: mediachain-indexer-ingest' + sys.argv[1] + ' directory_containing_compactsplit_files [normalizer_name or auto]')
            print ('Normalizer names:', normalizer_names.keys())
            exit(-1)
        
        path_glob = sys.argv[2]

        normalizer_name = sys.argv[3]

        if normalizer_name not in normalizer_names:
            print ('INVALID:',normalizer_name)
            print ('Normalizer names:', normalizer_names.keys())
            exit(-1)

        set_console_title(sys.argv[0] + ' ' + sys.argv[1] + ' ' + sys.argv[2] + ' ' + sys.argv[3] + ' ' + str(max_num))
    
    else:
        assert path_glob
    
    ## Simple:

    the_iter = lambda : iter_compactsplit(path_glob, max_num = max_num)
    
    iter_json = apply_normalizer(iter_json,
                                 normalizer_name,
                                 )
    
    cur = SimpleClient()
    cur.write_artefacts(the_iter)        
    
    ## NOTE - May not reach here due to gRPC hang bug.
    
    print ('DONE ALL',)

    
def send_compactsplit_to_indexer(path_glob = False,
                                 max_num = 0,
                                 index_name = mc_config.MC_INDEX_NAME,
                                 doc_type = mc_config.MC_DOC_TYPE,
                                 auto_dedupe = False,
                                 extra_translator_func = False,
                                 via_cli = False,
                                 ):
    """
    [TESTING_ONLY] Read from compactsplit dumps, write directly to Indexer. (Without going through blockchain.)
    
    Args:
        path_glob:             Directory containing compactsplit files.
        max_num:               End ingestion early after `max_num` records. For testing.
        index_name:            Name of Indexer index to populate.
        doc_type:              Name of Indexer doc type.
        extra_translator_func: Function, or name of function, that applies normalization / translation to records.
    """
    
    from mc_datasets import iter_compactsplit
    from mc_generic import set_console_title
    from mc_normalize import apply_normalizer, normalizer_names
    
    if via_cli:
        if (len(sys.argv) < 4):
            print ('Usage: mediachain-indexer-ingest'  + ' ' + sys.argv[1] + ' directory_containing_compactsplit_files [normalizer_name or auto]')
            print ('Normalizer names:', normalizer_names.keys())
            exit(-1)
        
        path_glob = sys.argv[2]

        normalizer_name = sys.argv[3]

        if normalizer_name not in normalizer_names:
            print ('INVALID:',normalizer_name)
            print ('Normalizer names:', normalizer_names.keys())
            exit(-1)
        
        set_console_title(sys.argv[0] + ' ' + sys.argv[1] + ' ' + sys.argv[2] + ' ' + sys.argv[3] + ' ' + str(max_num))        
    else:
        assert path_glob
        
    iter_json = lambda : iter_compactsplit(path_glob, max_num = max_num)
    
    iter_json = apply_normalizer(iter_json,
                                 normalizer_name,
                                 )

    rr = ingest_bulk(iter_json = iter_json)
    

    if auto_dedupe:
        ## TODO: automatically do this for now, so we don't forget:
        import mc_models
        mc_models.dedupe_reindex_all()
    else:
        print 'NOT AUTOMATICALLY RUNNING DEDUPE.'

    return rr

def send_gettydump_to_indexer(max_num = 0,
                              getty_path = False,
                              index_name = mc_config.MC_INDEX_NAME,
                              doc_type = mc_config.MC_DOC_TYPE,
                              auto_dedupe = False,
                              via_cli = False,
                              *args,
                              **kw):
    """
    [DEPRECATED] Read Getty dumps, write directly to Indexer. (Without going through blockchain.)
    
    Args:
        getty_path: Path to getty image JSON. `False` to get path from command line args.
        index_name: Name of Indexer index to populate.
        doc_type:   Name of Indexer doc type.
    """

    print ('!!!DEPRECATED: Use `ingest_compactsplit_indexer` now instead.')
    
    if via_cli:
        if len(sys.argv) < 3:
            print 'Usage: ' + sys.argv[0] + ' ' + sys.argv[1] + ' getty_small/json/images/'
            exit(-1)
        
        getty_path = sys.argv[2]
    else:
        assert getty_path
    
    iter_json = mc_datasets.iter_json_getty(max_num = max_num,
                                            getty_path = getty_path,
                                            index_name = index_name,
                                            doc_type = doc_type,
                                            *args,
                                            **kw)

    ingest_bulk(iter_json = iter_json)

    if auto_dedupe:
        ## TODO: automatically do this for now, so we don't forget:
        import mc_models
        mc_models.dedupe_reindex_all()
    else:
        print 'NOT AUTOMATICALLY RUNNING DEDUPE.'




def search_by_image(fn = False,
                    limit = 5,
                    index_name = mc_config.MC_INDEX_NAME,
                    doc_type = mc_config.MC_DOC_TYPE,
                    via_cli = False,
                    ):
    """
    Command-line content-based image search.
    
    Example:
    $ mediachain-indexer-ingest ingest_gettydump
    $ mediachain-indexer-ingest search_by_image getty_small/downloads/thumb/5/3/1/7/531746924.jpg
    """
    
    if via_cli:
        if len(sys.argv) < 3:
            print 'Usage: ' + sys.argv[0] + ' ' + sys.argv[1] + ' <image_file_name> [limit_num] [index_name] [doc_type]'
            exit(-1)
        
        fn = sys.argv[2]
        
        if len(sys.argv) >= 4:
            limit = intget(sys.argv[3], 5)
        
        if len(sys.argv) >= 5:
            index_name = sys.argv[4]
        
        if len(sys.argv) >= 6:
            doc_type = sys.argv[5]
        
        if not exists(fn):
            print ('File Not Found:',fn)
            exit(-1)
    else:
        assert fn,'File name required.'
    
    with open(fn) as f:
        d = f.read()
    
    img_uri = shrink_and_encode_image(d)
    
    hh = requests.post(mc_config.MC_TEST_WEB_HOST + '/search',
                       headers = {'User-Agent':'MC_CLI 1.0'},
                       verify = False,
                       json = {"q_id":img_uri,
                               "limit":limit,
                               "include_self": True,
                               "index_name":index_name,
                               "doc_type":doc_type,
                               },
                       ).json()
    
    print pretty_print(hh)


def delete_index(index_name = mc_config.MC_INDEX_NAME,
                 doc_type = mc_config.MC_DOC_TYPE,
                 via_cli = False,
                 ):
    """
    Delete an Indexer index.
    """
    
    print('DELETE_INDEX',index_name)
    
    if mc_config.LOW_LEVEL:
        es = mc_neighbors.low_level_es_connect()
        
        if es.indices.exists(index_name):
            es.indices.delete(index = index_name)
        
    else:
        #NOT LOW_LEVEL:
        nes = mc_neighbors.high_level_connect(index_name = index_name,
                                              doc_type = doc_type,
                                              index_settings = index_settings,
                                              use_custom_parallel_bulk = use_aggressive,
                                              )
        
        nes.delete_index()
    
    print ('DELETED',index_name)


def refresh_index(index_name = mc_config.MC_INDEX_NAME,
                  via_cli = False,
                  ):
    """
    Refresh an Indexer index. NOTE: newly inserted / updated items are not searchable until index is refreshed.
    """
    
    if mc_config.LOW_LEVEL:
        print ('REFRESHING', index_name)
        es.indices.refresh(index = index_name)
        print ('REFRESHED')
        rr = es.count(index_name)['count']
    else:
        nes.refresh_index()
        rr = nes.count()

def refresh_index_repeating(index_name = mc_config.MC_INDEX_NAME,
                            repeat_interval = 600,
                            via_cli = False,
                            ):
    """
    Repeatedly refresh Indexer indexes at specified interval.

    TODO: delay refresh if a refresh was already called elsewhere.
    """
    
    while True:
        refresh_index(index_name = index_name)
        sleep_loud(repeat_interval)


def config(via_cli = False):
    """
    Print config.
    """
    
    print_config(mc_config.cfg)


functions=['receive_blockchain_into_indexer',
           'send_compactsplit_to_blockchain',
           'send_compactsplit_to_indexer',
           'send_gettydump_to_indexer',
           'delete_index',
           'refresh_index',
           'refresh_index_repeating',
           'search_by_image',
           'config',
           'tail_blockchain',
           ]

def main():
    setup_main(functions,
               globals(),
                'mediachain-indexer-ingest',
               )

if __name__ == '__main__':
    main()

