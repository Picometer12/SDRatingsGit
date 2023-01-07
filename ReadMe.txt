This is unfinished and cobbled together by someone who doesn't know what they're doing. Use at your own risk. I haven't done much data validation yet, so leave batch count and batch size at 1 and type things carefully. 

Dump SDRatings.py and the two folders into scripts folder of Automatic1111. 

Both folders contain editable text files.

--- Using SDRatings ---

Each line in SDRatings is currently in the format:
keywordName(Group1:rating1:numberOfTimesrated1,Group2:rating2)
the last colon and numberofTimesrated is optional and will be assumed to be 0 if missing. SDRatigns will update it the first time the keyword is rated.

ex: Anton Fadeev(Overall:2000:5, ConceptArtist:2200:5, CartoonArtist:1500)


To rate keywords, put keyword (literally type keyword) into your prompt, and put the group names in the rated groups field. When you generate, two keywords that have all groups listed will be selected, and the same prompts will be repeated except keyword will be replaced with keyword1 or keyword2. After generation, you can vote on whether you like left or right better and the ratings will be adjusted. Clicking Can't decide will generate two more sets of images with the same keywords and new seeds. 

AristList.xlsx is an excel spreadsheet that I used to help populate SDRatings.txt since I haven't built in anything for managing this in Automatic1111 yet. 


--- Compatible with wildcards --- 
To use a wildcard, put __NameOfWildCardFile__ into your prompt and a random line from NameOfWildCardFile.txt in wildcards folder will be substituted.

