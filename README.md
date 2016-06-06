
## Search and Dedupe for Mediachain

Entry Point               |  Info
--------------------------|---------------------
mediachain-indexer-dedupe | (Re-)Generate deduplication lookup indexes.
mediachain-indexer-ingest | Ingest media from local sources or Mediachain API, for search & dedupe.
mediachain-indexer-web    | Search & dedupe REST API.
mediachain-indexer-eval   | Evaluate and score models against benchmarks.
mediachain-indexer-test   | Demos and tests.


## Getting Started

#### Core Setup

1) Install Elasticsearch. Version 2.3.2 or higher recommended.
  - [General Instructions](https://www.elastic.co/guide/en/elasticsearch/reference/current/_installation.html).
  - OSX: `brew install elasticsearch`
  - Linux: Check with your distribution.

2) Launch elasticsearch server.

```
$ elasticsearch
```

3) Install Indexer:

```
$ pip install git+https://github.com/mediachain/mediachain-indexer.git
```

4) Run any of the entry points above to see sub-commands:

```
$ mediachain-indexer-ingest

USAGE: python mc_ingest.py <function_name>

Available Functions:
getty_create_dumps...................... Quick and dirty Getty API scraper.
ingest_bulk_blockchain.................. Ingest media from Mediachain blockchain.
ingest_bulk_gettydump................... Ingest media from Getty data dumps into Indexer.
config.................................. Print current environment variables.
```

5) Inspect environment variables and adjust as necessary:

```
$ mediachain-indexer-ingest config
MC_DOC_TYPE="image"
MC_DOC_TYPE_CID_TO_CLUSTER="clusters"
MC_DOC_TYPE_MID_TO_CID="cluster_nums"
MC_GETTY_KEY=""
MC_INDEX_NAME="getty_test"
MC_INDEX_NAME_CID_TO_CLUSTER="clustering_baseline_cid_to_cluster"
MC_INDEX_NAME_MID_TO_CID="clustering_baseline_mid_to_cid"
MC_NUMBER_OF_REPLICAS="0"
MC_NUMBER_OF_SHARDS="1"
```


#### Quick Test

6) Run a basic sanity check demo:

```
$ mediachain-indexer-test sanity_check
```

#### Full Setup

7) Alternatively, grab small Getty testing dataset:

```
$ GETTY_KEY="<your_getty_key>" mediachain-indexer-ingest getty_create_dumps
```

8) Ingest Getty dataset:

```
$ mediachain-indexer-ingest ingest_bulk_gettydump
```

Or, ingest from Mediachain blockchain:

```
$ mediachain-indexer-ingest ingest_bulk_blockchain
```


9) Deduplicate ingested media:

```
$ mediachain-indexer-dedupe dedupe_reindex 
```

10) Start REST API server:

```
$ mediachain-indexer-web web
```

11) Query the REST API:

Search by text:

```
$ curl "http://127.0.0.1:23456/search" -d '{"q":"crowd", "limit":5}'
{
    "next_page": null, 
    "prev_page": null, 
    "results": [
        {
            "_id": "getty_531746924", 
            "_index": "getty_test", 
            "_score": 0.08742375, 
            "_source": {
                "artist": "Tristan Fewings", 
                "caption": "CANNES, FRANCE - MAY 16:  A policeman watches the crowd in front of the Palais des Festival during the red carpet arrivals of the 'Loving' premiere during the 69th annual Cannes Film Festival on May 16, 2016 in Cannes, France.  (Photo by Tristan Fewings/Getty Images)", 
                "collection_name": "Getty Images Entertainment", 
                "date_created": "2016-05-16T00:00:00-07:00", 
                "editorial_source": "Getty Images Europe", 
                "keywords": "People Vertical Crowd Watching France Police Force Cannes Film Premiere Premiere Arrival Photography Film Industry Red Carpet Event Arts Culture and Entertainment International Cannes Film Festival Celebrities Annual Event Palais des Festivals et des Congres 69th International Cannes Film Festival Loving - 2016 Film", 
                "title": "'Loving' - Red Carpet Arrivals - The 69th Annual Cannes Film Festival"
            }, 
            "_type": "image"
        }
    ]
}
```

Search by media content:

```
$ curl "http://127.0.0.1:23456/search" -d '{"q_id":"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg==", "limit":5, "index_name":"mc_test", "doc_type":"mc_test_image"}'
{
    "next_page": null, 
    "prev_page": null, 
    "results": [
        {
            "_id": "getty_1234", 
            "_index": "mc_test", 
            "_score": 1.0, 
            "_source": {
                "artist": "test", 
                "caption": "test", 
                "collection_name": "test", 
                "date_created": "2016-05-31T17:41:06.929234", 
                "editorial_source": "", 
                "keywords": "test", 
                "title": "Crowd of people walking"
            }, 
            "_type": "mc_test_image"
        }
    ]
}
```

Search by ID:

```
$ curl "http://127.0.0.1:23456/search" -d '{"q_id":"getty_1234", "limit":5, "index_name":"mc_test", "doc_type":"mc_test_image"}'
{   
    "next_page": null,
    "prev_page": null,
    "results": [
        {   
            "_id": "getty_1234",
            "_index": "mc_test",
            "_score": 1.0,
            "_source": {
                "artist": "test artist",
                "caption": "test caption",
                "collection_name": "test collection name",
                "date_created": "2016-06-01T15:21:57.796894",
                "editorial_source": "test editorial source",
                "keywords": "test keywords",
                "title": "Crowd of People Walking"
            },
            "_type": "mc_test_image"
        }
    ]
}
```

Duplicate lookup by ID:

```
$ curl "http://127.0.0.1:23456/dupe_lookup" -d '{"q_media":"getty_531746790"}'
{
    "next_page": null, 
    "prev_page": null, 
    "results": [
        {
            "_id": "getty_1234"
        }
    ]
}
```


