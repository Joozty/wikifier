import sys, json, math
import numpy as np
from sklearn.naive_bayes import GaussianNB

from relatedness import WLVM, ESA
from indexer import loadTranslation, loadLinks

encyclopedic = True
if len(sys.argv) == 2 and sys.argv[1] == 'content':
	encyclopedic = False

if encyclopedic:
	relatedness_model = WLVM()
else:
	relatedness_model = ESA()

# read indexes
translation = loadTranslation()
links = loadLinks()

def getLinks(phrase):
	phrase = phrase.lower()
	if not phrase in links: return {}
	result = links[phrase.lower()]
	result.pop('', 0)
	return result

def getProbability(phrase):
	return links[phrase.lower()].get('', 0)

# constants
minimum_sense_probability = .02

avg = lambda l: float(sum(l))/len(l) if l else 0

def features(article, data, target):
	""" augment each linked phrase in article with it's commonness, relatedness and context_quality

	article: includes text and annotations of an article
	returns whole article with augmented links
	"""

	global baseline_judgement

	# links without ambiguity in context (document)
	clear_links = filter(lambda annotation: len(getLinks(annotation['s'])) == 1 and annotation['u'] in translation, article['annotations'])

	# todo parallel weight calculation
	for link in clear_links:
		link['u'] = translation[link['u']]

	for link in clear_links:
		relatednesses = []
		for link2 in clear_links:
			if link != link2:
				relatednesses.append(relatedness_model.relatedness(link['u'], link2['u']))
		avg_relatedness = avg(relatednesses)

		# link probability effect
		link['weight'] = avg([avg_relatedness, getProbability(link['s'])])
	
	for annotation in article['annotations']:
		candidate_links = getLinks(annotation['s'])
		all_count = float(sum(candidate_links.values()))

		# filter candidate_links with minimum_sense_probability
		candidate_links = dict(filter(lambda (link, count): (count / all_count) > minimum_sense_probability, candidate_links.items()))
		
		# baseline_judgement as the most common link selection
		# if len(candidate_links) and annotation['u'] == max(candidate_links): baseline_judgement += 1
		
		context_quality = sum([clear_link['weight'] for clear_link in clear_links])
		for link, count in candidate_links.items():
			commonness = count / all_count
			relatedness = avg([clear_link['weight'] * relatedness_model.relatedness(link, clear_link['u'])  for clear_link in clear_links]) # weighted average of link relatedness

			data.append([commonness, relatedness, context_quality])
			target.append([int(link) == annotation['u'], annotation['o']])


articles = [json.loads(article) for article in open('data/samples.txt')]
train_size = int(len(articles) * .8)

# train
baseline_judgement = 0
data, target = [], []
for article in articles[:train_size]:
	features(article, data, target)
data = np.array(data, dtype=float)
target = np.array([t[0] for t in target], dtype=bool)

disambiguator = GaussianNB()
disambiguator.fit(data, target)

# test
baseline_judgement = 0
data, target = [], []
for article in articles[train_size:]:
	features(article, data, target)
data = np.array(data, dtype=float)
target = np.array(target)

predict = disambiguator.predict(data)
predict_proba = disambiguator.predict_proba(data)

# mesurements on data
tp = float((predict[predict == target[:, 0]] == True).sum())
data_precision = tp / (predict == True).sum()
data_recall = tp / (target[:, 0] == True).sum()

# fill results
results = np.append(target, predict_proba, axis=1)
indices = []
i, count = 0, 0
last_offset = -1
for result in results:
	if last_offset != result[1]:
		if count:
			indices.append((i-count, i))
		last_offset = result[1]
		count = 0
	i += 1; count += 1
indices.append((i-count, i))

# mesurements on links
judgements = []
for index in indices:
	link = results[index[0]:index[1]]
	mi = link[:, 3].argmax()
	judgements.append([link[mi][0] == 1, link[mi][3]])
judgements = np.array(judgements)

precision = 1 # that's it
recall = float(judgements[:, 0].sum()) / len(judgements)
baseline_recall = float(baseline_judgement) / len(judgements)

# wrong judgements: judgements[judgements[:, 0] == 0]
